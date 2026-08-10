import logging
from asyncio import gather
from contextlib import suppress
from time import time
from typing import Any, cast
from urllib.parse import quote

from crawl4ai import AsyncWebCrawler, CacheMode
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

from .models import Torrent
from .parser import (
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
    "1337x.to": {"parser": x1337_parse},
}

crawler = AsyncWebCrawler(config=BROWSER_CONFIG, always_bypass_cache=True)


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------
logger = logging.getLogger("Torrent Search")


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
    await ensure_trackers()
    enabled = list(WEBSITES.items())
    if sources is not None:
        enabled = [(s, d) for s, d in enabled if s in sources]
    async with crawler:
        results = await gather(*(_scrape_source(s, d, query) for s, d in enabled))
    return [r for r in results if r is not None]


async def search_torrents(
    query: str,
    sources: list[str] | None = None,
) -> list[Torrent]:
    """
    Search for torrents on all enabled sources.
    Corresponds to GET /torrents

    Args:
        query: Search query.
        sources: List of valid sources to scrape from.

    Returns:
        A list of torrent results.
    """
    start_time = time()
    scraped_results: list[str] = await scrape_torrents(query, sources=sources)
    torrents: list[Torrent] = []
    with suppress(Exception):
        torrents = extract_torrents(scraped_results)
        print(f"Successfully extracted results in {time() - start_time:.2f} sec.")
        return torrents
    logger.warning(
        "Failed to extract results for query '%s'. Returning empty list.", query
    )
    return torrents
