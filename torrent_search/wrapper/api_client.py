from sys import argv

from rich import print as pr
from ygg_torrent import ygg_api

from .models import Torrent

# from .utils import format_torrent


class TorrentSearchApi:
    """A client for interacting with the TorrentSearch API."""

    def __init__(self):
        """
        Initializes the API client.
        """
        pass

    def search_torrents(self, query: str = "") -> list[Torrent] | None:
        """
        Get a list of torrents.
        Corresponds to GET /torrents

        Args:
            query: Search query.

        Returns:
            A list of torrent results or an error dictionary.
        """
        return ygg_api.search_torrents(query)

    def get_torrent_details(
        self, torrent_id: int, with_magnet_link: bool = False
    ) -> Torrent | None:
        """
        Get details about a specific torrent.
        Corresponds to GET /torrent/{torrent_id}

        Args:
            torrent_id: The ID of the torrent.

        Returns:
            Detailed torrent result.
        """
        if torrent_id < 1:
            pr("torrent_id must be >= 1")
            return None
        resp = ygg_api.get_torrent_details(torrent_id)
        if not resp:
            pr("Failed to get torrent details")
            return None
        torrent = Torrent(**resp.model_dump())
        if with_magnet_link:
            torrent.magnet_link = self.get_magnet_link(torrent_id)
        return torrent

    def get_magnet_link(self, torrent_id: int) -> str | None:
        """
        Get the magnet link for a specific torrent.

        Args:
            torrent_id: The ID of the torrent.

        Returns:
            The magnet link as a string or None.
        """
        try:
            return ygg_api.get_magnet_link(torrent_id)
        except Exception as e:
            pr(f"Failed to get magnet link: {e}")
            return None


if __name__ == "__main__":
    QUERY = argv[1] if len(argv) > 1 else None
    if not QUERY:
        pr("Please provide a search query.")
        exit(1)
    client = TorrentSearchApi()
    found_torrents = client.search_torrents(QUERY)
    if found_torrents:
        pr(client.get_torrent_details(found_torrents[0].id, with_magnet_link=True))
    else:
        pr("No torrents found")
