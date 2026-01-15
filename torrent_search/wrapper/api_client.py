from asyncio import gather, run, to_thread
from os import getenv, makedirs
from pathlib import Path
from sys import argv
from typing import Any

from aiocache import cached
from fr_torrent_search import fr_torrent_api

from .models import Cache, Torrent
from .scraper import WEBSITES, search_torrents

FOLDER_TORRENT_FILES: Path = Path(getenv("FOLDER_TORRENT_FILES") or "./torrents")
makedirs(FOLDER_TORRENT_FILES, exist_ok=True)

SOURCES: list[str] = list(WEBSITES.keys())
EXCLUDE_SOURCES: list[str] = list()
INCLUDE_FR_SOURCES = getenv("EXCLUDE_FR_SOURCES", "false").lower() in ["0", "false"]
FR_SOURCES: set[str] = set()

if INCLUDE_FR_SOURCES:
    fr_torrent_api.ensure_initialized()
    FR_SOURCES = {source for source in fr_torrent_api.api_names}
    SOURCES = list(set(SOURCES).union(FR_SOURCES))

if excluded_sources := getenv("EXCLUDE_SOURCES"):
    EXCLUDE_SOURCES = list(
        set(EXCLUDE_SOURCES).union(
            {source.strip() for source in excluded_sources.split(",")}
        )
    )
    SOURCES = list(set(SOURCES) - set(EXCLUDE_SOURCES))


def key_builder(
    _namespace: str, _fn: Any, *args: tuple[Any], **kwargs: dict[str, Any]
) -> str:
    key = {
        "query": args[0] if len(args) > 0 else "",
        "max_items": args[1] if len(args) > 1 else 10,
    } | kwargs
    return str(key)


class TorrentSearchApi:
    """A client for searching torrents."""

    CACHE: Cache = Cache()

    def available_sources(self) -> list[str]:
        """Get the list of available torrent sources."""
        return SOURCES

    @cached(ttl=300, key_builder=key_builder)  # 5min
    async def search_torrents(
        self,
        query: str,
        max_items: int = 10,
    ) -> list[Torrent]:
        """
        Search for torrents on available sources.

        Args:
            query: Search query.
            max_items: Maximum number of items to return.

        Returns:
            A list of torrent results.
        """
        found_torrents: list[Torrent] = []

        # Prepare search tasks
        search_tasks = []
        if any(source not in FR_SOURCES for source in SOURCES):
            search_tasks.append(search_torrents(query, SOURCES))
        if INCLUDE_FR_SOURCES and any(source in FR_SOURCES for source in SOURCES):
            search_tasks.append(
                to_thread(
                    fr_torrent_api.search_torrents,
                    query,
                    max_items=max_items,
                    exclude=EXCLUDE_SOURCES,
                )
            )

        # Execute searches in parallel
        if search_tasks:
            results = await gather(*search_tasks)
            result_index = 0
            if any(source not in FR_SOURCES for source in SOURCES):
                found_torrents.extend(results[result_index])
                result_index += 1
            if INCLUDE_FR_SOURCES and any(source in FR_SOURCES for source in SOURCES):
                found_torrents.extend(
                    [
                        Torrent.format(**torrent.model_dump())
                        for torrent in results[result_index]
                    ]
                )

        found_torrents = list(
            sorted(
                found_torrents,
                key=lambda torrent: torrent.seeders + torrent.leechers,
                reverse=True,
            )
        )[:max_items]

        for torrent in found_torrents:
            torrent.prepend_info(query, max_items)

        self.CACHE.clean()  # Clean cache routine
        self.CACHE.update(found_torrents)
        return found_torrents

    async def get_torrent(self, torrent_id: str) -> str | None:
        """
        Get the magnet link or torrent filepath for a previously found torrent.

        Args:
            torrent_id: The ID of the torrent.

        Returns:
            The magnet link or torrent filepath as a string, else None.
        """
        found_torrent: Torrent | None = self.CACHE.get(torrent_id)

        try:
            query, max_items, source, ref_id = Torrent.extract_info(torrent_id)
        except Exception:
            print(f"Invalid torrent ID: {torrent_id}")
            return None

        if not found_torrent:  # Missing or uncached
            torrents: list[Torrent] = await self.search_torrents(query, max_items)
            found_torrent = next(
                (torrent for torrent in torrents if torrent.id == torrent_id), None
            )
            if found_torrent:
                source = found_torrent.source

        if found_torrent and INCLUDE_FR_SOURCES and source in FR_SOURCES:
            result = fr_torrent_api.get_torrent(ref_id, output_dir=FOLDER_TORRENT_FILES)
            if result and isinstance(result, str):
                if result.endswith(".torrent"):
                    found_torrent.torrent_file = str(FOLDER_TORRENT_FILES / result)
                else:
                    found_torrent.magnet_link = result

        self.CACHE.clean()  # Clean cache routine

        if found_torrent:
            if found_torrent.torrent_file:
                return found_torrent.torrent_file
            elif found_torrent.magnet_link:
                return found_torrent.magnet_link
        return None

    async def cli(self) -> None:
        """
        Command line interface for the API.
        """
        query = argv[1] if len(argv) > 1 else None
        if query:
            found_torrents: list[Torrent] = await self.search_torrents(
                query, max_items=100
            )
            if found_torrents:
                found_sources = set()
                for t in found_torrents:
                    found_sources.add(t.source)
                    print(
                        f"{t.id} ({t.seeders}|{t.leechers}|{t.downloads}) - {t.filename}"
                    )
                print(f"Fetching: {found_torrents[0].id}")
                print(f"Result: {await self.get_torrent(found_torrents[0].id)}")
                print(
                    f"Found Sources (Excluded: {EXCLUDE_SOURCES}): {found_sources} | Found Torrents: {len(found_torrents)}"
                )
            else:
                print("No torrents found")
        else:
            print("Please provide a search query.")


if __name__ == "__main__":
    run(TorrentSearchApi().cli())
