import logging
from copy import deepcopy
from os import getenv
from typing import Any

from dotenv import load_dotenv
from fastmcp import FastMCP

from .wrapper import Torrent, TorrentSearchApi

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TorrentSearch")

mcp: FastMCP[Any] = FastMCP("TorrentSearch Tool")

torrent_search_api = TorrentSearchApi()

INCLUDE_LINKS = str(getenv("INCLUDE_LINKS")).lower() == "true"
SOURCES = torrent_search_api.available_sources()


@mcp.resource("data://torrent_sources")
def available_sources() -> list[str]:
    """Get the list of available torrent sources."""
    return SOURCES


@mcp.tool()
def prepare_search_query(user_intent: str, search_query: str) -> str:
    """Always use this tool to prepare a query for `search_torrents`.
    Properly split the user's intention and the actual search query (space-separated keywords) to avoid unfruitful results.
    # Instructions:
    - `user_intent`: Must reflect user's overall intention (e.g., "last episode of Breaking Bad", "season 5 of Breaking Bad", "complete series of Breaking Bad").
    - `search_query`: The actual search terms, consisting of lowercase, space-separated keywords. Do not add generic terms (e.g., "movie", "series"), common prefixes (e.g., "the", "a", "and"), or extra information (e.g., episode name, resolution, codec). For TV series, use `sXXeYY` for specific episodes (e.g., "breaking bad s05e16"), `sXX` for complete seasons (e.g., "breaking bad s05") and only the show name for complete series (e.g., "breaking bad").
    - For non-English languages, if requested, add the language code (e.g., "fr", "spa") to the query.
    """
    return "Ready to search for torrents."


@mcp.tool()
async def search_torrents(query: str) -> str:
    """Searches for torrents using a query (space-separated keywords) and returns a list of torrent results.
    # Instructions:
    - To be called after `prepare_search_query`.
    - Prioritize results using the following hierarchy: is 1080p > smaller file size > is x265 > max seeders+leechers.
    - Recommend up to 3 of the best results, **always** providing filename, file size, seeders/leechers, date, source, and an ultra concise reason.
    - If the search results are too broad, suggest the user provide more specific keywords.
    - Keep recommendations and suggestions concise.
    """
    logger.info(f"Searching for torrents: {query}")
    found_torrents: list[Torrent] = await torrent_search_api.search_torrents(query)
    if not found_torrents:
        return "No torrents found"
    elif found_torrents and not INCLUDE_LINKS:  # Greatly reduce token usage
        shorted_torrents = deepcopy(found_torrents)  # Leave cache intact
        for torrent in shorted_torrents:
            torrent.magnet_link = None
            torrent.torrent_file = None
        return "\n".join([str(torrent) for torrent in shorted_torrents])
    return "\n".join([str(torrent) for torrent in found_torrents])


@mcp.tool()
async def get_torrent_info(torrent_id: str) -> str:
    """Get info for a specific torrent by id."""
    logger.info(f"Getting info for torrent: {torrent_id}")
    torrent: Torrent | None = await torrent_search_api.get_torrent_details(torrent_id)
    return str(torrent) if torrent else "Torrent not found"


@mcp.tool()
async def get_magnet_link_or_torrent_file(torrent_id: str) -> str:
    """Get the magnet link or torrent filepath for a specific torrent by id."""
    logger.info(f"Getting magnet link or torrent filepath for torrent: {torrent_id}")
    magnet_link_or_torrent_file: (
        str | None
    ) = await torrent_search_api.get_magnet_link_or_torrent_file(torrent_id)
    return (
        magnet_link_or_torrent_file or "Torrent, magnet link or torrent file not found"
    )
