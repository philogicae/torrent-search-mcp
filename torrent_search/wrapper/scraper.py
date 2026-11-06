import logging
from asyncio import gather, wait_for
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

# Fresh window shared by the per-source listings and the aggregate popular
# cache. Once it expires, the next popular request refetches the stale sources
# before answering; a failed refetch falls back to the last known-good listing.
POPULAR_TTL: float = 300.0
# source -> (fetched_at, per_source used for the fetch, listing text)
_popular_cache: dict[str, tuple[float, int | None, str]] = {}


async def _scrape_source(source: str, parser: SourceParser, query: str) -> str | None:
    started = time()
    try:
        processed_text = await wait_for(parser(query), timeout=SOURCE_TIMEOUT)
        logger.debug(
            "Source %s returned %d rows in %.2fs.",
            source,
            max(processed_text.count("\n") - 1, 0),
            time() - started,
        )
        return f"SOURCE -> {source}\n{processed_text}"
    except Exception as e:  # noqa: BLE001 - keep the source out of the search
        logger.warning("Error scraping %s for query '%r': %s", source, query, e)
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
    started = time()
    try:
        text = await wait_for(fn(per_source), timeout=SOURCE_TIMEOUT)
        logger.debug(
            "Popular source %s returned %d rows in %.2fs.",
            name,
            max(text.count("\n") - 1, 0),
            time() - started,
        )
        return f"SOURCE -> {name}\n{text}"
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


async def _popular_source(
    name: str,
    fn: Callable[[int | None], Awaitable[str]],
    per_source: int | None,
    refresh: bool = False,
) -> str | None:
    entry = _popular_cache.get(name)
    if (
        not refresh
        and entry is not None
        and _popular_covers(entry[1], per_source)
        and time() - entry[0] < POPULAR_TTL
    ):
        return entry[2]
    text = await _fetch_popular_text(name, fn, per_source)
    if text is not None:
        _popular_cache[name] = (time(), per_source, text)
        return text
    # Failed refresh: keep the source in the listing with its last known-good
    # text when that text covers the request, instead of dropping the section.
    if entry is not None and _popular_covers(entry[1], per_source):
        return entry[2]
    return None


async def popular_torrents(
    sources: list[str] | None = None,
    per_source: int | None = None,
    refresh: bool = False,
) -> list[Torrent]:
    """
    Get the current top/popular listings from all supporting sources.

    Uses only plain HTTP endpoints. A source listing older than ``POPULAR_TTL``
    (5 minutes) is refetched before the aggregate is returned; an explicit
    ``refresh`` bypasses every cached listing.

    Args:
        sources: List of valid sources to include.
        per_source: Optional maximum number of results kept per source
            (best first). None keeps everything the source returned.
        refresh: When true, every source is fetched again (no cache is read)
            and its cached listing is replaced. Used by the Web UI POPULAR
            button so a click always re-scrapes.

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
        *(_popular_source(name, fn, per_source, refresh) for name, fn in enabled)
    )
    torrents: list[Torrent] = []
    for text in results:
        if text is None:
            continue
        found = extract_torrents([text])
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
