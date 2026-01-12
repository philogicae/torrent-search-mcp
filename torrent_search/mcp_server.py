import logging
from copy import deepcopy
from os import getenv
from typing import Any

from dotenv import load_dotenv
from fastmcp import FastMCP

from .wrapper import Torrent, TorrentSearchApi

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Torrent Search")

mcp: FastMCP[Any] = FastMCP("Torrent Search Tool")

torrent_search_api = TorrentSearchApi()

INCLUDE_LINKS = str(getenv("INCLUDE_LINKS")).lower() == "true"
SOURCES = torrent_search_api.available_sources()


@mcp.resource("data://torrent_sources")
def available_sources() -> list[str]:
    """Get the list of available torrent sources."""
    return SOURCES


@mcp.tool()
async def search_torrents(
    user_intent: str,
    query: str,
) -> str:
    """Perfom an advanced torrent search across multiple providers.

    # Arguments:
    - `user_intent`: Must reflect user's overall intention (e.g., "last episode of Breaking Bad", "season 5 of Breaking Bad", "complete Breaking Bad series").
    - `query`: Optimized keywords for search. MUST be lowercase and space-separated.

    # Query Construction Rules:
    - **NO** generic terms: remove "movie", "series", "torrent", "download".
    - **NO** filler words: remove "the", "a", "an", "and", "of", "with".
    - **NO** technical tags: do NOT add "1080p", "x264", "bluray", or episode titles.
    - **TV Shows**:
        - Specific episode: `[show name] sXXeYY` (e.g., "shogun s01e05")
        - Full season: `[show name] sXX` (e.g., "shogun s01")
        - Full series: `[show name]` (e.g., "shogun")
    - **Language**: Add `multi` ONLY if the user specifically requests a non-French or multi-language version.

    # Result Analysis & Ranking:
    1. **Quality**: Prefer 1080p over 720p or 4k (unless requested).
    2. **Efficiency**: Prefer x265/HEVC for better quality/size ratio.
    3. **Health**: Maximize seeders + leechers.
    4. **Size**: Prefer smaller files within the same quality bracket.

    # Response Requirements:
    - Recommend the **top 3** results maximum.
    - For each recommendation, include: Filename, Size, Seeds/Leechs, Date, Source, and a 1-sentence "Why this?" reason.
    - If results are poor or irrelevant, suggest specific keywords to improve the search.
    """
    _ = user_intent
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
async def get_torrent(torrent_id: str) -> str:
    """Get the magnet link or torrent filepath for a specific torrent by id."""
    logger.info(f"Getting magnet link or torrent filepath for torrent: {torrent_id}")
    result: str | None = await torrent_search_api.get_torrent(torrent_id)
    return result or "Torrent not found"
