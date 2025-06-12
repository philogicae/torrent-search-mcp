from typing import Any

from fastmcp import FastMCP

from .wrapper import Torrent, TorrentSearchApi

mcp: FastMCP[Any] = FastMCP(
    name="Torrent Search Server",
    instructions="This server provides tools for interacting with TorrentSearch API.",
)
torrent_search_api = TorrentSearchApi()
SOURCES = torrent_search_api.available_sources()


@mcp.resource("data://torrent_sources")
def available_sources() -> list[str]:
    """Get the list of available torrent sources."""
    return SOURCES


@mcp.tool()
async def search_torrents(
    query: str,
    sources: list[str] | None = None,
    max_items: int = 10,
) -> list[Torrent]:
    """Search for torrents on sources [thepiratebay.org, nyaa.si, yggtorrent]."""
    return await torrent_search_api.search_torrents(
        query, sources=sources, max_items=max_items
    )


@mcp.tool()
def get_ygg_torrent_details(
    torrent_id: int,
    with_magnet_link: bool = False,
) -> Torrent | None:
    """Get details about a specific torrent coming from YGG Torrent source only."""
    return torrent_search_api.get_ygg_torrent_details(torrent_id, with_magnet_link)


@mcp.tool()
def get_ygg_magnet_link(torrent_id: int) -> str | None:
    """Get the magnet link for a specific torrent coming from YGG Torrent source only."""
    return torrent_search_api.get_ygg_magnet_link(torrent_id)
