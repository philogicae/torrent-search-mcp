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

# Popular sections ordered by traffic (TorrentFreak 2026 ranking), using
# the public display domains (scraping keys are mapped in api_client).
SOURCE_ORDER = [
    "thepiratebay.org",
    "1337x.to",
    "uindex.org",
    "eztvx.to",
    "yts.vg",
    "nyaa.si",
    "fitgirl-repacks.site",
    "subsplease.org",
    "bittorrented.com",
]


def _source_rank(source: str) -> int:
    try:
        return SOURCE_ORDER.index(source)
    except ValueError:
        return len(SOURCE_ORDER)


_api_client: httpx.AsyncClient | None = None


def _api() -> httpx.AsyncClient:
    """Shared HTTP client for remote-API mode."""
    global _api_client
    if _api_client is None:
        _api_client = httpx.AsyncClient(base_url=API_BASE_URL, timeout=20)
    return _api_client


async def _api_get_json(path: str, params: dict[str, str] | None = None) -> Any:
    response = await _api().get(path, params=params)
    response.raise_for_status()
    return response.json()


async def _api_get_text(path: str) -> str:
    response = await _api().get(path)
    response.raise_for_status()
    return response.text


async def _api_post_json(path: str, params: dict[str, str] | None = None) -> Any:
    response = await _api().post(path, params=params)
    response.raise_for_status()
    return response.json()


async def _fetch_torrents(
    path: str, params: dict[str, str], *, post: bool = False
) -> list[Torrent]:
    """Fetch torrent listings from the remote REST API."""
    request_json = _api_post_json if post else _api_get_json
    data = await request_json(path, params)
    return [Torrent.model_validate(row) for row in data]


@mcp.tool()
async def available_sources() -> list[str]:
    """Get the list of available torrent sources."""
    if API_BASE_URL:
        return await _api_get_json("/sources")
    return SOURCES


def _torrent_line(torrent: Torrent) -> str:
    if not INCLUDE_LINKS:  # Greatly reduce token usage
        torrent = torrent.model_copy(update={"magnet_link": None})
    return str(torrent)


def _format_torrents(found_torrents: list[Torrent], *, by_source: bool = False) -> str:
    if not by_source:
        return "\n".join(_torrent_line(torrent) for torrent in found_torrents)
    groups: dict[str, list[Torrent]] = {}
    for torrent in found_torrents:
        groups.setdefault(torrent.source or "unknown", []).append(torrent)
    blocks: list[str] = []
    for source in sorted(groups, key=lambda s: (_source_rank(s), s)):
        lines = [f"== {source} =="]
        # Sections read best with the healthiest swarms first.
        ranked = sorted(groups[source], key=lambda t: t.seeders, reverse=True)
        lines.extend(_torrent_line(torrent) for torrent in ranked)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


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

    # Pruned magnets (PRUNE_MAGNET_LINKS=true):
    - Pruned magnets look like magnet:?xt=urn:btih:INFO_HASH&dn=URL_ENCODED_DISPLAY_NAME (trackers stripped).
    - When reusing one, replace the dn value with a clean/readable/normalized re-encoded display name:
      percent-decode it, tidy separators (dots/underscores/dashes -> spaces), strip release noise
      (e.g. quality/tag suffixes) unless requested, then percent-encode the result for use in the URI.
    """
    _ = user_intent
    logger.info(f"Searching for torrents: {query}")
    if API_BASE_URL:
        found_torrents = await _fetch_torrents(
            "/torrent/search", {"query": query, "max_items": "20"}, post=True
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
            description="How many top results to keep per source (default 20).",
        ),
    ] = 20,
) -> str:
    """Get the most popular torrents right now across providers with an official top listing.

    Output is grouped per source (thepiratebay.org, uindex.org, 1337x.to, eztvx.to,
    yts.vg, nyaa.si), keeping up to `per_source` results per site, each site's
    entries pre-ranked by swarm health.

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
    return _format_torrents(found_torrents, by_source=True)


@mcp.tool()
async def get_torrent(
    torrent_id: Annotated[
        str,
        Field(
            description="Torrent ID returned by a previous search_torrents or popular_torrents call."
        ),
    ],
) -> str:
    """Get the magnet link for a specific torrent by id.

    Note on pruned magnets (when PRUNE_MAGNET_LINKS=true): pruned magnets keep
    only magnet:?xt=urn:btih:INFO_HASH&dn=URL_ENCODED_DISPLAY_NAME — every
    &tr= tracker is stripped. When re-using one, replace the dn value with a
    clean/readable/normalized re-encoded display name: percent-decode it,
    tidy separators (dots/dashes -> spaces), then percent-encode the result.
    """
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


@mcp.tool()
async def authorize_webapp(
    code: Annotated[
        str,
        Field(description="Pairing code shown in the Web UI 'Telegram Access' gate."),
    ],
    chat_id: Annotated[
        str,
        Field(
            description="The owner's Telegram chat id the webapp access is bound to."
        ),
    ],
) -> str:
    """Authorize a browser on the Torrent Search webapp via its pairing code.

    Ask the user for the code displayed in their Telegram Access gate, then call this
    tool once with it and your Telegram chat id. Codes are single-use and expire
    after ~15 minutes. The browser polls until confirmed, then stores its token.
    """
    logger.info("Authorizing webapp access for chat %s", chat_id)
    secret = getenv("TORRENT_SEARCH_API_KEY")
    if not secret:
        return (
            "Webapp authorization is disabled: set TORRENT_SEARCH_API_KEY "
            "(same value on the REST API server) to enable pairing approvals."
        )
    if not API_BASE_URL:
        return (
            "authorize_webapp requires TORRENT_SEARCH_API_URL: pairing "
            "state lives on the REST API server that serves the Web UI."
        )
    response = await _api().post(
        "/telegram/auth/register",
        params={"code": code, "chat_id": chat_id},
        headers={"Authorization": f"Bearer {secret}"},
    )
    if response.status_code == 404:
        return "Unknown or expired pairing code. Ask the user for the current code shown in the gate."
    if response.status_code == 401:
        return "Authorization rejected: TORRENT_SEARCH_API_KEY does not match the API server."
    response.raise_for_status()
    return "Access granted. The Web UI will confirm within a few seconds and remember this browser."


@mcp.tool()
async def torrent_webapp() -> str:
    """Present the Torrent Search web UI and its Telegram pairing access system.

    Returns the webapp URL (WEBUI_URL) plus how a browser gets authorized:
    the user opens the URL, a pairing code appears, and calling
    authorize_webapp with that code grants the browser permanent access.
    """
    url = getenv("WEBUI_URL", "").rstrip("/")
    if not url:
        return (
            "Web UI URL not configured. Set WEBUI_URL (e.g. http://localhost:8000 "
            "or a public URL) to advertise the webapp."
        )
    return (
        f"Torrent Search web UI: {url}\n"
        "A dark/light terminal-broadsheet UI: multi-source torrent search, "
        "per-site popular tiles, magnet links, and a Telegram relay for sending "
        "torrents to the owner's chat.\n"
        "Access is pairing-gated: on first visit the site shows a one-time "
        "pairing code. Ask the user for that code, then call the "
        "authorize_webapp tool with it (and your Telegram chat id) to grant "
        "the browser permanent access. Codes expire after ~15 minutes."
    )
