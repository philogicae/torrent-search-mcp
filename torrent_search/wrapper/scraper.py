import logging
from asyncio import CancelledError, Lock, Task, create_task, gather, sleep
from collections.abc import Awaitable, Callable
from contextlib import suppress
from os import getenv
from time import monotonic, time
from typing import Any, cast
from urllib.parse import quote

from crawl4ai import AsyncWebCrawler, CacheMode
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

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
    parse_result,
    subsplease_parse,
    uindex_parse,
    x1337_parse,
    yts_parse,
)

# ---------------------------------------------------------------------------
# Crawler Configuration
# ---------------------------------------------------------------------------
BROWSER_CONFIG = BrowserConfig(
    browser_type="chromium",
    headless=True,
    text_mode=True,
    light_mode=True,
)
DEFAULT_MD_GENERATOR = DefaultMarkdownGenerator(
    options={
        "ignore_images": True,
        "ignore_links": False,
        "skip_internal_links": True,
        "escape_html": True,
    }
)
DEFAULT_CRAWLER_RUN_CONFIG = CrawlerRunConfig(
    markdown_generator=DEFAULT_MD_GENERATOR,
    remove_overlay_elements=True,
    exclude_social_media_links=True,
    excluded_tags=["header", "footer", "nav"],
    remove_forms=True,
    cache_mode=CacheMode.DISABLED,
)

# ---------------------------------------------------------------------------
# Websites Registry
# ---------------------------------------------------------------------------
WEBSITES: dict[str, dict[str, str | list[str] | SourceParser]] = {
    "thepiratebay.org": {
        "search": "https://thepiratebay.org/search.php?q={query}&cat=0",
        "parsing": "html",
        "exclude_patterns": [
            "some_texts",  # Don't remove quoted attribute values
            "local_links",  # Don't remove </li> tags
            "single_angle_bracket",  # Don't remove HTML angle brackets
            "html_tags",  # Don't remove HTML tags in filters (do it in replacers)
            # But DO include ol_attributes filter
        ],
    },
    # Sources with a "parser" are fetched over HTTP (see parser.py)
    # and normalized to the same CSV text contract.
    "nyaa.si": {"parser": nyaa_parse},
    "yts.mx": {"parser": yts_parse},
    "apibay.org": {"parser": apibay_parse},
    "eztvx.to": {"parser": eztv_parse},
    "fitgirl-repacks.site": {"parser": fitgirl_parse},
    "subsplease.org": {"parser": subsplease_parse},
    "bittorrented.com": {"parser": bittorrented_parse},
    "uindex.org": {"parser": uindex_parse},
    "1337x.to": {"parser": x1337_parse},
}

CRAWLER_IDLE_TIMEOUT: float = float(getenv("CRAWLER_IDLE_TIMEOUT") or "120")

crawler = AsyncWebCrawler(config=BROWSER_CONFIG, always_bypass_cache=True)
_crawler_start_lock = Lock()
_crawler_idle_timer: Task[None] | None = None
_crawler_last_used: float = 0.0
_active_scrapes: int = 0

# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------
logger = logging.getLogger("Torrent Search")


async def _ensure_crawler_started() -> None:
    """Start the shared crawler once; ``arun`` keeps it warm afterwards.

    Concurrent first searches race on ``arun``'s implicit auto-start
    (not idempotent), so serialize the cold start behind a lock.
    """
    if not crawler.ready:
        async with _crawler_start_lock:
            if not crawler.ready:
                await crawler.start()


def _schedule_crawler_shutdown() -> None:
    """(Re)arm the idle shutdown; every new search postpones it."""
    global _crawler_idle_timer
    if CRAWLER_IDLE_TIMEOUT <= 0:  # disabled
        return
    if _crawler_idle_timer is not None:
        _crawler_idle_timer.cancel()
    _crawler_idle_timer = create_task(_close_idle_crawler())


async def _close_idle_crawler() -> None:
    """Release the shared browser after CRAWLER_IDLE_TIMEOUT idle seconds.

    Skipped when a scrape is still in flight; the next search transparently
    restarts the crawler.
    """
    try:
        await sleep(CRAWLER_IDLE_TIMEOUT)
    except CancelledError:
        return
    async with _crawler_start_lock:
        idle_for = monotonic() - _crawler_last_used
        if crawler.ready and not _active_scrapes and idle_for >= CRAWLER_IDLE_TIMEOUT:
            logger.info("Crawler idle for %.0fs, shutting down browser.", idle_for)
            with suppress(Exception):
                await crawler.close()
            crawler.ready = False  # close() does not reset the flag itself


async def _scrape_source(
    source: str,
    data: dict[str, str | list[str] | SourceParser],
    query: str,
) -> str | None:
    result: str | None = None
    try:
        parser = data.get("parser")
        if parser is not None:
            processed_text = await cast(SourceParser, parser)(query)
        else:
            url = str(data["search"]).format(query=quote(query))
            crawl_result: Any = await crawler.arun(  # type: ignore
                url=url, config=DEFAULT_CRAWLER_RUN_CONFIG
            )
            raw_content = (
                crawl_result.cleaned_html
                if data["parsing"] == "html"
                else crawl_result.markdown
            )
            processed_text = parse_result(
                raw_content,
                cast(list[str], data.get("exclude_patterns", [])),
            )
        result = f"SOURCE -> {source}\n{processed_text}"
    except Exception as e:  # noqa: BLE001 - keep the source out of the search
        logger.warning("Error scraping %s for query '%s': %s", source, query, e)
    return result


async def scrape_torrents(query: str, sources: list[str] | None = None) -> list[str]:
    """
    Scrape torrents from all enabled sources in parallel.

    Args:
        query: Search query.
        sources: List of valid sources to scrape from.

    Returns:
        A list of text results.
    """
    global _crawler_last_used, _active_scrapes
    await ensure_trackers()
    enabled = list(WEBSITES.items())
    if sources is not None:
        enabled = [(s, d) for s, d in enabled if s in sources]
    # Only launch/keep the browser when at least one enabled source needs it.
    uses_crawler = any(str(d.get("parsing")) == "html" for _, d in enabled)
    if uses_crawler:
        await _ensure_crawler_started()
        _crawler_last_used = monotonic()
        _active_scrapes += 1
    try:
        results = await gather(*(_scrape_source(s, d, query) for s, d in enabled))
    finally:
        if uses_crawler:
            _active_scrapes -= 1
            _crawler_last_used = monotonic()
            _schedule_crawler_shutdown()
    return [r for r in results if r is not None]


async def _popular_source(name: str, fn: Callable[[], Awaitable[str]]) -> str | None:
    try:
        return f"SOURCE -> {name}\n{await fn()}"
    except Exception as e:  # noqa: BLE001 - keep the source out of the listing
        logger.warning("Error fetching popular listing from %s: %s", name, e)
        return None


async def popular_torrents(
    sources: list[str] | None = None, per_source: int = 10
) -> list[Torrent]:
    """
    Get the current top/popular listings from all supporting sources.

    Uses only plain HTTP endpoints; no browser is started.

    Args:
        sources: List of valid sources to include.
        per_source: Maximum number of results kept per source (best first).

    Returns:
        A list of torrent results ranked by seeders + leechers.
    """
    per_source = max(1, per_source)
    start_time = time()
    await ensure_trackers()
    enabled = [
        (name, fn)
        for name, fn in POPULAR_SOURCES.items()
        if sources is None or name in sources
    ]
    results = await gather(*(_popular_source(name, fn) for name, fn in enabled))
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
        sources: List of valid sources to scrape from.

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
