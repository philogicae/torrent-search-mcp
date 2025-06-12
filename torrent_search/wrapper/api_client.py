from sys import argv

from ygg_torrent import ygg_api

from .models import Torrent
from .scraper import WEBSITES, search_torrents


class TorrentSearchApi:
    """A client for searching torrents on ThePirateBay, Nyaa and YGG Torrent."""

    WEBSITES = ["yggtorrent"] + list(WEBSITES.keys())

    def available_sources(self) -> list[str]:
        """Get the list of available torrent sources."""
        return self.WEBSITES

    async def search_torrents(
        self,
        query: str,
        sources: list[str] | None = None,
        max_items: int = 50,
    ) -> list[Torrent]:
        """
        Search for torrents on ThePirateBay, Nyaa and YGG Torrent.

        Args:
            query: Search query.
            sources: List of valid sources to scrape from.
            max_items: Maximum number of items to return.

        Returns:
            A list of torrent results or an error dictionary.
        """
        found_torrents = []
        if sources is None or any(source in sources for source in WEBSITES):
            found_torrents.extend(await search_torrents(query, sources=sources))
        if sources is None or "yggtorrent" in sources:
            ygg_torrents = ygg_api.search_torrents(query)
            if ygg_torrents:
                found_torrents.extend(
                    [
                        Torrent(**torrent.model_dump(), source="yggtorrent")
                        for torrent in ygg_torrents
                    ]
                )
        return list(
            sorted(
                found_torrents,
                key=lambda torrent: torrent.seeders + torrent.leechers,
                reverse=True,
            )
        )[:max_items]

    def get_ygg_torrent_details(
        self, ygg_torrent_id: int, with_magnet_link: bool = False
    ) -> Torrent | None:
        """
        Get details about a specific torrent coming from YGG Torrent source only.

        Args:
            ygg_torrent_id: The ID of the torrent.

        Returns:
            Detailed torrent result.
        """
        torrent = ygg_api.get_torrent_details(
            ygg_torrent_id, with_magnet_link=with_magnet_link
        )
        if not torrent:
            return None
        return Torrent(**torrent.model_dump(), source="yggtorrent")

    def get_ygg_magnet_link(self, ygg_torrent_id: int) -> str | None:
        """
        Get the magnet link for a specific torrent coming from YGG Torrent source only.

        Args:
            ygg_torrent_id: The ID of the torrent.

        Returns:
            The magnet link as a string or None.
        """
        return ygg_api.get_magnet_link(ygg_torrent_id)


if __name__ == "__main__":

    async def main() -> None:
        query = argv[1] if len(argv) > 1 else None
        if not query:
            print("Please provide a search query.")
            exit(1)
        client = TorrentSearchApi()
        torrents: list[Torrent] = await client.search_torrents(query)
        print(torrents)
        ygg = [torrent for torrent in torrents if torrent.source == "yggtorrent"]
        if ygg and ygg[0].id:
            print(client.get_ygg_torrent_details(ygg[0].id, with_magnet_link=True))
        else:
            print("No torrents found")

    from asyncio import run

    run(main())
