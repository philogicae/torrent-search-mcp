import logging
from asyncio import gather, wait_for
from collections.abc import Awaitable, Callable
from time import time

from .models import Torrent
from .parser import (
    POPULAR_SOURCES,
    SourceParser,
    apibay_parse,
    bittorrented_parse,
    ensure_trackers,
    extract_torrents,
    eztv_parse,
    fitgirl_parse,
    nyaa_parse,
    subsplease_parse,
    uindex_parse,
    x1337_parse,
    yts_parse,
)

# ---------------------------------------------------------------------------
# Websites Registry
# ---------------------------------------------------------------------------
# Every source is fetched over plain HTTP by its parser (see parser.py) and
# normalized to the same CSV text contract.
WEBSITES: dict[str, SourceParser] = {
    "nyaa.si": nyaa_parse,
    "yts.mx": yts_parse,
    "apibay.org": apibay_parse,  # official ThePirateBay API (shown as thepiratebay.org)
    "eztvx.to": eztv_parse,
    "fitgirl-repacks.site": fitgirl_parse,
    "subsplease.org": subsplease_parse,
    "bittorrented.com": bittorrented_parse,
    "uindex.org": uindex_parse,
    "1337x.to": x1337_parse,
}

# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------
logger = logging.getLogger("Torrent Search")

SOURCE_TIMEOUT: float = (
    30.0  # hard cap per source per request (yts mirror alone can take ~20s)
)


async def _scrape_source(source: str, parser: SourceParser, query: str) -> str | None:
    try:
        processed_text = await wait_for(parser(query), timeout=SOURCE_TIMEOUT)
        return f"SOURCE -> {source}\n{processed_text}"
    except Exception as e:  # noqa: BLE001 - keep the source out of the search
        logger.warning("Error scraping %s for query '%s': %s", source, query, e)
        return None


async def scrape_torrents(query: str, sources: list[str] | None = None) -> list[str]:
    """
    Fetch torrents from all enabled sources in parallel.

    Args:
        query: Search query.
        sources: List of valid sources to fetch from.

    Returns:
        A list of text results.
    """
    await ensure_trackers()
    enabled = [
        (name, parser)
        for name, parser in WEBSITES.items()
        if sources is None or name in sources
    ]
    results = await gather(*(_scrape_source(s, p, query) for s, p in enabled))
    return [r for r in results if r is not None]


async def _popular_source(
    name: str, fn: Callable[[int | None], Awaitable[str]], per_source: int | None
) -> str | None:
    try:
        return f"SOURCE -> {name}\n{await wait_for(fn(per_source), timeout=SOURCE_TIMEOUT)}"
    except Exception as e:  # noqa: BLE001 - keep the source out of the listing
        logger.warning("Error fetching popular listing from %s: %s", name, e)
        return None


async def popular_torrents(
    sources: list[str] | None = None, per_source: int | None = None
) -> list[Torrent]:
    """
    Get the current top/popular listings from all supporting sources.

    Uses only plain HTTP endpoints.

    Args:
        sources: List of valid sources to include.
        per_source: Optional maximum number of results kept per source
            (best first). None keeps everything the source returned.

    Returns:
        A list of torrent results ranked by seeders + leechers.
    """
    start_time = time()
    await ensure_trackers()
    enabled = [
        (name, fn)
        for name, fn in POPULAR_SOURCES.items()
        if sources is None or name in sources
    ]
    results = await gather(
        *(_popular_source(name, fn, per_source) for name, fn in enabled)
    )
    torrents: list[Torrent] = []
    for text in results:
        if text is None:
            continue
        try:
            found = extract_torrents([text])
        except Exception:  # noqa: BLE001 - skip a single broken source
            logger.warning("Failed to extract popular results for one source.")
            continue
        found.sort(key=lambda torrent: torrent.seeders + torrent.leechers, reverse=True)
        torrents.extend(found[:per_source])
    torrents.sort(key=lambda torrent: torrent.seeders + torrent.leechers, reverse=True)
    logger.info(
        "Extracted %d popular torrents in %.2f sec.", len(torrents), time() - start_time
    )
    return torrents


async def search_torrents(
    query: str,
    sources: list[str] | None = None,
) -> list[Torrent]:
    """
    Search for torrents on all enabled sources.

    Args:
        query: Search query.
        sources: List of valid sources to fetch from.

    Returns:
        A list of torrent results.
    """
    start_time = time()
    scraped_results: list[str] = await scrape_torrents(query, sources=sources)
    try:
        torrents = extract_torrents(scraped_results)
    except Exception:  # noqa: BLE001 - degrade to empty result set
        logger.warning(
            "Failed to extract results for query '%s'. Returning empty list.", query
        )
        return []
    logger.info(
        "Extracted %d torrents in %.2f sec.", len(torrents), time() - start_time
    )
    return torrents
