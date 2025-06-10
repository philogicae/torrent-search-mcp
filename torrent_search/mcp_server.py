from fastmcp import FastMCP

from .wrapper import Torrent, TorrentSearchApi

mcp = FastMCP(
    "TorrentSearchServer",
    instructions="""
        This server provides tools for interacting with the TorrentSearch API.
    """,
)
torrent_search_api = TorrentSearchApi()


@mcp.tool()
def search_torrents(
    query: str,
    limit: int | None = None,
) -> list[Torrent]:
    """Search for torrent files."""
    return (torrent_search_api.search_torrents(query) or [])[: limit or 50]


@mcp.tool()
def get_torrent_details(
    torrent_id: int,
    with_magnet_link: bool = False,
) -> Torrent | None:
    """Get details about a specific torrent."""
    return torrent_search_api.get_torrent_details(torrent_id, with_magnet_link)


@mcp.tool()
def get_magnet_link(torrent_id: int) -> str | None:
    """Get the magnet link for a specific torrent."""
    return torrent_search_api.get_magnet_link(torrent_id)
