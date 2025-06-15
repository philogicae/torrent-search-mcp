from typing import Any

from fastmcp import FastMCP

from .wrapper import Torrent, TorrentSearchApi

mcp: FastMCP[Any] = FastMCP(
    name="Torrent Search Server",
    instructions="""This tool searches for torrents based on the user's provided space-separated keywords and returns a list of results.
    Recommend the best torrent to choose from the results, following this priority rule: match 1080p resolution > is x265 encoded > has great number of seeds+leechers > has small file size.
    If query or results are too wide or heterogeneous for a clear search or top pick, suggest user adds more specific keywords to narrow down the search.
    Never add unnecessary keywords (like: movie, serie, etc.) to user's query, they are rarely part of torrent names.
    Comply to user's request and be concise in your recommendation and suggestions.""",
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
    """Search for torrents on sources [thepiratebay.org, nyaa.si, yggtorrent]. If sources is not specified, all sources are included by default."""
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
