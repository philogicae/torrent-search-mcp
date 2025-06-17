from sys import argv
from typing import Any

from aiocache import cached
from ygg_torrent import ygg_api

from .models import Torrent
from .scraper import WEBSITES, search_torrents


def key_builder(
    namespace: str, fn: Any, *args: tuple[Any], **kwargs: dict[str, Any]
) -> str:
    return str(
        {"query": args[0] if len(args) > 0 else "", "sources": None, "max_items": 10}
        | kwargs
    )


class TorrentSearchApi:
    """A client for searching torrents on ThePirateBay, Nyaa and YGG Torrent."""

    WEBSITES = ["yggtorrent"] + list(WEBSITES.keys())
    CACHE: dict[str, Torrent] = {}

    def available_sources(self) -> list[str]:
        """Get the list of available torrent sources."""
        return self.WEBSITES

    @cached(ttl=300, key_builder=key_builder)  # type: ignore[misc] # 5min
    async def search_torrents(
        self,
        query: str,
        sources: list[str] | None = None,
        max_items: int = 10,
    ) -> list[Torrent]:
        """
        Search for torrents on ThePirateBay, Nyaa and YGG Torrent.

        Args:
            query: Search query.
            sources: List of valid sources to scrape from.
            max_items: Maximum number of items to return.

        Returns:
            A list of torrent results.
        """
        found_torrents: list[Torrent] = []
        if sources is None or any(source in sources for source in WEBSITES):
            found_torrents.extend(await search_torrents(query, sources=sources))
        if sources is None or "yggtorrent" in sources:
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
        self.CACHE.update({torrent.id: torrent for torrent in found_torrents})
        return found_torrents

    async def get_torrent_details(
        self, torrent_id: str, original_search_params: dict[str, Any] | None = None
    ) -> Torrent | None:
        """
        Get details about a previously found torrent.

        Args:
            torrent_id: The ID of the torrent.
            original_search_params: The original query parameters used to search for the torrent. Can be omitted if from YGG Torrent.

        Returns:
            Detailed torrent result or None.
        """
        found_torrent: Torrent | None = None
        if torrent_id in self.CACHE:
            found_torrent = self.CACHE[torrent_id]

        print(torrent_id)
        source, real_id = torrent_id.split("-", 1)
        if source == "yggtorrent":
            if not found_torrent:
                ygg_torrent = ygg_api.get_torrent_details(
                    int(real_id), with_magnet_link=True
                )
                if ygg_torrent:
                    found_torrent = Torrent.format(
                        **ygg_torrent.model_dump(), source="yggtorrent"
                    )
            elif not found_torrent.magnet_link:
                found_torrent.magnet_link = ygg_api.get_magnet_link(int(real_id))
        elif not found_torrent and original_search_params:
            torrents: list[Torrent] = await self.search_torrents(
                **original_search_params
            )
            for torrent in torrents:
                if torrent.id == torrent_id:
                    found_torrent = torrent
                    break
        if found_torrent:
            self.CACHE[torrent_id] = found_torrent
        else:
            del self.CACHE[torrent_id]
        return found_torrent

    async def get_magnet_link(
        self, torrent_id: str, original_search_params: dict[str, Any] | None = None
    ) -> str | None:
        """
        Get the magnet link for a previously found torrent.

        Args:
            torrent_id: The ID of the torrent.
            original_search_params: The original query parameters used to search for the torrent. Can be omitted if from YGG Torrent.

        Returns:
            The magnet link as a string or None.
        """
        found_torrent: Torrent | None = await self.get_torrent_details(
            torrent_id, original_search_params
        )
        if found_torrent and found_torrent.magnet_link:
            return found_torrent.magnet_link
        return None


if __name__ == "__main__":

    async def main() -> None:
        query = argv[1] if len(argv) > 1 else None
        if not query:
            print("Please provide a search query.")
            exit(1)
        client = TorrentSearchApi()
        original_search_params = {"query": query, "max_items": 10}
        torrents: list[Torrent] = await client.search_torrents(**original_search_params)
        if torrents:
            for torrent in torrents:
                print(
                    await client.get_torrent_details(torrent.id, original_search_params)
                )
        else:
            print("No torrents found")

    from asyncio import run

    run(main())
