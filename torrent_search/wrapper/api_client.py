from asyncio import run
from os import getenv, makedirs
from pathlib import Path
from sys import argv
from typing import Any

from aiocache import cached

from .models import Cache, Torrent
from .scraper import WEBSITES, search_torrents

FOLDER_TORRENT_FILES: Path = Path(getenv("FOLDER_TORRENT_FILES") or "./torrents")
makedirs(FOLDER_TORRENT_FILES, exist_ok=True)

SOURCES: list[str] = list(WEBSITES.keys())
EXCLUDE_SOURCES: list[str] = list()

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
        query = query.lower()
        found_torrents: list[Torrent] = []

        # Search across all enabled sources
        found_torrents = await search_torrents(query, SOURCES)

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
            query, max_items = Torrent.extract_info(torrent_id)[:2]
        except Exception:
            print(f"Invalid torrent ID: {torrent_id}")
            return None

        if not found_torrent:  # Missing or uncached
            torrents: list[Torrent] = await self.search_torrents(query, max_items)
            found_torrent = next(
                (torrent for torrent in torrents if torrent.id == torrent_id), None
            )

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
