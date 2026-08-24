import logging
from os import getenv
from typing import Annotated, Any

import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP
from pydantic import Field

from .wrapper import Torrent, TorrentSearchApi

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Torrent Search")

mcp: FastMCP[Any] = FastMCP("Torrent Search Tools")

torrent_search_api = TorrentSearchApi()

INCLUDE_LINKS = str(getenv("INCLUDE_LINKS")).lower() == "true"
SOURCES = torrent_search_api.available_sources()

# Remote mode: when TORRENT_SEARCH_API_URL is set (e.g. http://api:8000), the
# tools proxy the REST API instead of scraping locally. Unset = standalone.
API_BASE_URL = getenv("TORRENT_SEARCH_API_URL", "").rstrip("/")

_api_client: httpx.AsyncClient | None = None


def _api() -> httpx.AsyncClient:
    """Shared HTTP client for remote-API mode."""
    global _api_client
    if _api_client is None:
        _api_client = httpx.AsyncClient(base_url=API_BASE_URL, timeout=60)
    return _api_client


async def _api_get_json(path: str, params: dict[str, str] | None = None) -> Any:
    response = await _api().get(path, params=params)
    response.raise_for_status()
    return response.json()


async def _api_get_text(path: str) -> str:
    response = await _api().get(path)
    response.raise_for_status()
    return response.text


async def _fetch_torrents(path: str, params: dict[str, str]) -> list[Torrent]:
    """Fetch torrent listings from the remote REST API."""
    data = await _api_get_json(path, params)
    return [Torrent.model_validate(row) for row in data]


logger.info(
    "MCP mode: %s", f"remote API ({API_BASE_URL})" if API_BASE_URL else "standalone"
)


@mcp.tool()
async def available_sources() -> list[str]:
    """Get the list of available torrent sources."""
    if API_BASE_URL:
        return await _api_get_json("/sources")
    return SOURCES


def _format_torrents(found_torrents: list[Torrent]) -> str:
    if not INCLUDE_LINKS:  # Greatly reduce token usage
        return "\n".join(
            str(torrent.model_copy(update={"magnet_link": None}))
            for torrent in found_torrents
        )
    return "\n".join([str(torrent) for torrent in found_torrents])


@mcp.tool()
async def search_torrents(
    user_intent: Annotated[
        str,
        Field(
            description="User's overall intention (e.g. 'latest episode of Breaking Bad')."
        ),
    ],
    query: Annotated[
        str,
        Field(
            description=(
                "Optimized search keywords, lowercase and space-separated. Strip generic"
                " terms (movie, torrent, download), filler words (the, a, of) and technical"
                " tags (1080p, h265, bluray) unless explicitly requested. TV shows:"
                " 'name sXXeYY' for episodes, 'name sXX' for seasons. Add 'multi' only if a"
                " multi-language version is requested."
            )
        ),
    ],
) -> str:
    """Perform an advanced torrent search across multiple providers.

    # Result Analysis & Ranking:
    1. **Quality**: Prefer 1080p or 4k, over 720p.
    2. **Efficiency**: Prefer h265/HEVC for better quality/size ratio.
    3. **Health**: Maximize seeders + leechers.
    4. **Size**: Prefer smaller files within the same quality bracket.
    5. **Language**: Ultimately, if multiple equivalent options are available, choose the one with more languages.

    # Response Requirements:
    - Recommend the **top 3-5** results maximum.
    - For each recommendation, include: Filename, Size, Seeds/Leechs, Date, Source, and a 1-sentence "Why this?" reason.
    - If results are poor, irrelevant or too diverse, suggest specific keywords to improve the search.
    """
    _ = user_intent
    logger.info(f"Searching for torrents: {query}")
    if API_BASE_URL:
        found_torrents = await _fetch_torrents(
            "/torrent/search", {"query": query, "max_items": "20"}
        )
    else:
        found_torrents = await torrent_search_api.search_torrents(query)
    if not found_torrents:
        return "No torrents found"
    return _format_torrents(found_torrents)


@mcp.tool()
async def popular_torrents(
    per_source: Annotated[
        int,
        Field(
            ge=1,
            description="How many top results to keep per source (default 10).",
        ),
    ] = 10,
) -> str:
    """Get the most popular torrents right now across providers with an official top listing.

    Keeps up to `per_source` results from each supporting source
    (apibay, uindex, 1337x, YTS, nyaa, EZTV), merged and pre-ranked by swarm health (seeders + leechers).

    # Response Requirements:
    - Recommend the **top 5-10** results maximum, focused on latest releases.
    - For each recommendation, include: Filename, Size, Seeds/Leechs, Date, Source, and a 1-sentence "Why this?" reason.
    """
    logger.info(f"Fetching popular torrents (per_source={per_source})")
    if API_BASE_URL:
        found_torrents = await _fetch_torrents(
            "/torrent/popular", {"per_source": str(per_source)}
        )
    else:
        found_torrents = await torrent_search_api.popular_torrents(per_source)
    if not found_torrents:
        return "No torrents found"
    return _format_torrents(found_torrents)


@mcp.tool()
async def get_torrent(
    torrent_id: Annotated[
        str,
        Field(
            description="Torrent ID returned by a previous search_torrents or popular_torrents call."
        ),
    ],
) -> str:
    """Get the magnet link for a specific torrent by id."""
    logger.info(f"Getting magnet link for torrent: {torrent_id}")
    if API_BASE_URL:
        try:
            return await _api_get_text(f"/torrent/{torrent_id}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return "Torrent not found"
            raise
    result: str | None = await torrent_search_api.get_torrent(torrent_id)
    return result or "Torrent not found"
