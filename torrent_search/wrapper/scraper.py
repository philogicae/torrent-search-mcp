import logging
from asyncio import Task, create_task, gather, wait_for
from collections.abc import Awaitable, Callable
from time import time

from .models import Torrent
from .parser import (
    POPULAR_SOURCES,
    SourceParser,
    apibay_parse,
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

# Per-source fresh window for popular listings: within it a source is served
# from its own cache, so a popular call only refetches genuinely stale sources.
POPULAR_TTL: float = 300.0
# source -> (fetched_at, per_source used for the fetch, listing text)
_popular_cache: dict[str, tuple[float, int | None, str]] = {}
# source -> in-flight background refresh while a stale entry is served
_popular_refreshing: dict[str, Task[None]] = {}


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


async def _fetch_popular_text(
    name: str, fn: Callable[[int | None], Awaitable[str]], per_source: int | None
) -> str | None:
    try:
        return f"SOURCE -> {name}\n{await wait_for(fn(per_source), timeout=SOURCE_TIMEOUT)}"
    except Exception as e:  # noqa: BLE001 - keep the source out of the listing
        logger.warning("Error fetching popular listing from %s: %s", name, e)
        return None


def _popular_covers(used: int | None, requested: int | None) -> bool:
    """True when a listing fetched with ``used`` satisfies ``requested``.

    ``None`` means the full listing; any integer is a best-N truncation, so a
    fuller fetch can serve a smaller request but never the other way around.
    """
    if used is None:
        return True
    return requested is not None and used >= requested


async def _refresh_popular(
    name: str, fn: Callable[[int | None], Awaitable[str]], per_source: int | None
) -> None:
    """Background refresh of a stale popular listing (keeps the best coverage)."""
    try:
        text = await _fetch_popular_text(name, fn, per_source)
        if text is not None:
            existing = _popular_cache.get(name)
            if existing is None or _popular_covers(per_source, existing[1]):
                _popular_cache[name] = (time(), per_source, text)
    finally:
        _popular_refreshing.pop(name, None)


async def _popular_source(
    name: str, fn: Callable[[int | None], Awaitable[str]], per_source: int | None
) -> str | None:
    entry = _popular_cache.get(name)
    if entry is not None and _popular_covers(entry[1], per_source):
        if time() - entry[0] < POPULAR_TTL:
            return entry[2]
        # Stale but usable: answer now and refresh in the background, so a
        # slow source never holds back the aggregate listing.
        if name not in _popular_refreshing:
            _popular_refreshing[name] = create_task(
                _refresh_popular(name, fn, per_source)
            )
        return entry[2]
    text = await _fetch_popular_text(name, fn, per_source)
    if text is not None:
        _popular_cache[name] = (time(), per_source, text)
    return text


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
