from os import getenv, makedirs
from pathlib import Path
from sys import argv
from typing import Any

from aiocache import cached
from ygg_torrent import ygg_api

from .models import Cache, Torrent
from .scraper import WEBSITES, search_torrents

PREFER_TORRENT_FILES: bool = str(getenv("PREFER_TORRENT_FILES")).lower() == "true"
FOLDER_TORRENT_FILES: Path = Path(getenv("FOLDER_TORRENT_FILES") or "./torrents")
makedirs(FOLDER_TORRENT_FILES, exist_ok=True)

EXCLUDE_SOURCES: set[str] = set()
SOURCES: list[str] = ["yggtorrent"] + list(WEBSITES.keys())

YGG_ENABLED: bool = len(str(getenv("YGG_PASSKEY"))) == 32
if not YGG_ENABLED:
    EXCLUDE_SOURCES.add("yggtorrent")

if excluded_sources := getenv("EXCLUDE_SOURCES"):
    EXCLUDE_SOURCES = EXCLUDE_SOURCES.union(
        {source.lower().strip() for source in excluded_sources.split(",")}
    )
    SOURCES = [source for source in SOURCES if source not in EXCLUDE_SOURCES]


def key_builder(
    _namespace: str, _fn: Any, *args: tuple[Any], **kwargs: dict[str, Any]
) -> str:
    key = {
        "query": args[0] if len(args) > 0 else "",
        "max_items": args[1] if len(args) > 1 else 10,
    } | kwargs
    return str(key)


class TorrentSearchApi:
    """A client for searching torrents on ThePirateBay, Nyaa and YGG Torrent."""

    CACHE: Cache = Cache()

    def available_sources(self) -> list[str]:
        """Get the list of available torrent sources."""
        return SOURCES

    @cached(ttl=300, key_builder=key_builder)  # type: ignore[misc] # 5min
    async def search_torrents(
        self,
        query: str,
        max_items: int = 10,
    ) -> list[Torrent]:
        """
        Search for torrents on ThePirateBay, Nyaa and YGG Torrent.

        Args:
            query: Search query.
            max_items: Maximum number of items to return.

        Returns:
            A list of torrent results.
        """
        found_torrents: list[Torrent] = []
        if any(source != "yggtorrent" for source in SOURCES):
            found_torrents.extend(await search_torrents(query, SOURCES))
        if "yggtorrent" in SOURCES:
            found_torrents.extend(
                [
                    Torrent.format(**torrent.model_dump(), source="yggtorrent")
                    for torrent in ygg_api.search_torrents(query)
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

    async def get_torrent_details(self, torrent_id: str) -> Torrent | None:
        """
        Get details about a previously found torrent.

        Args:
            torrent_id: The ID of the torrent.

        Returns:
            Detailed torrent result or None.
        """
        found_torrent: Torrent | None = self.CACHE.get(torrent_id)

        try:
            query, max_items, source, ref_id = Torrent.extract_info(torrent_id)
        except Exception:
            print(f"Invalid torrent ID: {torrent_id}")
            return None

        if source == "yggtorrent":
            if not found_torrent:  # Missing or uncached
                ygg_torrent = ygg_api.get_torrent_details(
                    int(ref_id), with_magnet_link=not PREFER_TORRENT_FILES
                )
                if ygg_torrent:
                    found_torrent = Torrent.format(
                        **ygg_torrent.model_dump(), source="yggtorrent"
                    )
                    found_torrent.prepend_info(query, max_items)
            if found_torrent:
                if PREFER_TORRENT_FILES:
                    if not found_torrent.torrent_file:
                        filename = ygg_api.download_torrent_file(
                            int(ref_id), output_dir=FOLDER_TORRENT_FILES
                        )
                        if filename:
                            found_torrent.torrent_file = str(
                                FOLDER_TORRENT_FILES / filename
                            )
                elif not found_torrent.magnet_link:  # Cached but missing magnet link
                    found_torrent.magnet_link = ygg_api.get_magnet_link(int(ref_id))
        elif not found_torrent:  # Missing or uncached
            torrents: list[Torrent] = await self.search_torrents(query, max_items)
            found_torrent = next(
                (torrent for torrent in torrents if torrent.id == torrent_id), None
            )

        self.CACHE.clean()  # Clean cache routine
        return found_torrent

    async def get_magnet_link_or_torrent_file(self, torrent_id: str) -> str | None:
        """
        Get the magnet link or torrent filepath for a previously found torrent.

        Args:
            torrent_id: The ID of the torrent.

        Returns:
            The magnet link or torrent filepath as a string, else None.
        """
        found_torrent: Torrent | None = await self.get_torrent_details(torrent_id)
        if found_torrent:
            if PREFER_TORRENT_FILES and found_torrent.torrent_file:
                return found_torrent.torrent_file
            elif found_torrent.magnet_link:
                return found_torrent.magnet_link
        return None


if __name__ == "__main__":

    async def main() -> None:
        query = argv[1] if len(argv) > 1 else None
        if not query:
            print("Please provide a search query.")
            exit(1)
        client = TorrentSearchApi()
        torrents: list[Torrent] = await client.search_torrents(query, max_items=5)
        if torrents:
            for torrent in torrents:
                print(await client.get_magnet_link_or_torrent_file(torrent.id))
        else:
            print("No torrents found")

    from asyncio import run

    run(main())
