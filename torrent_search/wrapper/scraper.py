from re import DOTALL, Pattern, compile, search, sub
from time import time
from typing import Any
from urllib.parse import quote

from crawl4ai import AsyncWebCrawler, CacheMode
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from pydantic import ValidationError

from .models import Torrent

# Crawler Configuration
BROWSER_CONFIG = BrowserConfig(
    browser_type="chromium",
    headless=True,
    text_mode=True,
    light_mode=True,
)
DEFAULT_MD_GENERATOR = DefaultMarkdownGenerator(
    options=dict(
        ignore_images=True,
        ignore_links=False,
        skip_internal_links=True,
        escape_html=True,
    )
)
DEFAULT_CRAWLER_RUN_CONFIG = CrawlerRunConfig(
    markdown_generator=DEFAULT_MD_GENERATOR,
    remove_overlay_elements=True,
    exclude_social_media_links=True,
    excluded_tags=["header", "footer", "nav"],
    remove_forms=True,
    cache_mode=CacheMode.DISABLED,
)

# Websites Configuration
FILTERS: dict[str, Pattern[str]] = {
    "full_links": compile(
        r"(http|https|ftp):[/]{1,2}[a-zA-Z0-9.]+[a-zA-Z0-9./?=+~_\-@:%#&]*"
    ),
    "backslashes": compile(r"\\"),
    "local_links": compile(r"(a href=)*(<|\")\/[a-zA-Z0-9./?=+~()_\-@:%#&]*(>|\")* *"),
    "some_texts": compile(r' *"[a-zA-Z ]+" *'),
    "empty_angle_brackets": compile(r" *< *> *"),
    "empty_curly_brackets": compile(r" *\{ *\} *"),
    "empty_parenthesis": compile(r" *\( *\) *"),
    "empty_brackets": compile(r" *\[ *\] *"),
    "tags": compile(
        r"<img[^>]*>|<a[^>]*>(?:alt|src)=|(?<=<a )(?:alt|src)=|(?<=<img )(?:alt|src)"
    ),
    "input_elements": compile(r"<input[^>]*>"),
    "date": compile(r'<label title=("[a-zA-Z0-9()+: ]+"|>)'),
}
REPLACERS: dict[str, tuple[Pattern[str], str]] = {
    # Basic text cleaning
    "weird_spaces": (compile(r"\u00A0"), " "),
    "spans": (compile(r"</?span>"), " | "),
    "weird spaced bars": (compile(r" *\|[ \|]+"), " | "),
    "double_quotes": (compile(r'"[" ]+'), ""),
    "single_angle_bracket": (compile(r"<|>"), ""),
    "gt": (compile("&gt;"), " -"),
    "amp": (compile("&amp;"), "&"),
    # Line formatting
    "bad_starting_spaced_bars": (compile(r"\n[\| ]+"), "\n"),
    "bad_ending_spaces": (compile(r" +\n"), "\n"),
    "duplicated_spaces": (compile(r" {2,4}"), " "),
    # Size formatting
    "size": (compile(r"([\d.]+[\s ]?[KMGT])i?B"), r"\1B"),
    # ThePirateBay specific fixes
    "thepiratebay_labels": (
        compile(r"Category.*?ULed by", DOTALL),
        "category | filename | date | magnet_link | size | seeders | leechers | uploader",
    ),
    # Nyaa specific fixes
    "nyaa_remove_click_here_line": (
        compile(r"^\[Click he*?\]\n"),
        "",
    ),
    "nyaa_header_block": (
        compile(r"Category \| Name \| Link \|Size \|Date \|\s*\r?\n[\|-]+\s*\r?\n"),
        "category | filename | magnet_link | size | date | seeders | leechers | downloads\n",
    ),
    "nyaa_remove_comments": (
        compile(r"\|\( \"\d+ comments?\"\)"),
        "|",
    ),
    "nyaa_clean_category_and_name_column_data": (
        compile(r'([\|\n])[^\|\n]+\"([^"\|]+)\"[^\|]+'),
        r"\1 \2 ",
    ),
    "nyaa_clean_link_column_data": (
        compile(r"\|\((magnet:\?[^)]+)\)"),
        r"| \1",
    ),
    "nyaa_fix_leading_spaces": (
        compile(r"\n\s+"),
        "\n",
    ),
    # Final formatting
    "to_csv": (compile(r" \| *"), ";"),
}
WEBSITES: dict[str, dict[str, str | list[str]]] = {
    "thepiratebay.org": dict(
        search="https://thepiratebay.org/search.php?q={query}",
        parsing="html",
        exclude_patterns=[],
    ),
    "nyaa.si": dict(
        search="https://nyaa.si/?f=0&c=0_0&q={query}&s=seeders&o=desc",
        parsing="markdown",
        exclude_patterns=["local_links"],
    ),
}

crawler = AsyncWebCrawler(config=BROWSER_CONFIG, always_bypass_cache=True)


def parse_result(
    text: str, exclude_patterns: list[str] | None = None, max_chars: int = 5000
) -> str:
    """
    Parse the text result.

    Args:
        text: The text to parse.
        exclude_patterns: List of patterns to exclude.
        max_chars: Maximum number of characters to return.

    Returns:
        The parsed text.
    """
    text = text.split("<li>", 1)[-1].replace("<li>", "")
    for name, pattern in FILTERS.items():
        if exclude_patterns and name in exclude_patterns:
            continue
        text = pattern.sub("", text)
    for name, replacer_config in REPLACERS.items():
        if exclude_patterns and name in exclude_patterns:
            continue
        pattern, replacement_str = replacer_config
        text = pattern.sub(replacement_str, text)
    if len(text) > max_chars:
        safe_truncate_pos = text.rfind("\n", 0, max_chars)
        if safe_truncate_pos == -1:
            text = text[:max_chars]
        else:
            text = text[:safe_truncate_pos]
    text = sub(r"\n{2,}", "\n", text)
    return text.strip()


async def scrape_torrents(query: str, sources: list[str] | None = None) -> list[str]:
    """
    Scrape torrents from ThePirateBay and Nyaa.

    Args:
        query: Search query.
        sources: List of valid sources to scrape from.

    Returns:
        A list of text results.
    """
    results_list = []
    async with crawler:
        for source, data in WEBSITES.items():
            if sources is None or source in sources:
                url = str(data["search"]).format(query=quote(query))
                try:
                    crawl_result: Any = await crawler.arun(  # type: ignore
                        url=url, config=DEFAULT_CRAWLER_RUN_CONFIG
                    )
                    processed_text = parse_result(
                        (
                            crawl_result.cleaned_html  # type: ignore
                            if data["parsing"] == "html"
                            else crawl_result.markdown  # type: ignore
                        ),
                        list(data.get("exclude_patterns", [])),
                    )
                    results_list.append(f"SOURCE -> {source}\n{processed_text}")
                except Exception as e:
                    print(f"Error scraping {source} for query '{query}' at {url}: {e}")
    return results_list


def extract_torrents(texts: list[str]) -> list[Torrent]:
    """
    Extract torrents from the parsed texts.

    Args:
        texts: The texts to extract torrents from.

    Returns:
        A list of torrent results.
    """
    torrents: list[Torrent] = []
    for text in texts:
        source, content = text.split("\n", 1)
        if "No results" in content:
            continue
        source = source[10:]
        data = content.splitlines()
        headers = data[0].split(";")
        for line in data[1:]:
            try:
                values = line.split(";")
                if len(values) > len(headers):
                    extra_count = len(values) - len(headers)
                    if len(values) > 1:
                        combined_filename = " - ".join(values[1 : 1 + extra_count + 1])
                        markdown_match = search(r"\[(.*?)\]\(", combined_filename)
                        if markdown_match:
                            values[1] = markdown_match.group(1)
                        else:
                            values[1] = combined_filename
                        del values[2 : 2 + extra_count]

                torrent = dict(zip(headers, values)) | {"source": source}
                torrents.append(Torrent.format(**torrent))
            except ValidationError:
                continue
            except Exception:
                continue
    return torrents


async def search_torrents(
    query: str,
    sources: list[str] | None = None,
    max_retries: int = 1,
) -> list[Torrent]:
    """
    Search for torrents on ThePirateBay and Nyaa.
    Corresponds to GET /torrents

    Args:
        query: Search query.
        sources: List of valid sources to scrape from.
        max_retries: Maximum number of retries.

    Returns:
        A list of torrent results.
    """
    start_time = time()
    scraped_results: list[str] = await scrape_torrents(query, sources=sources)
    torrents: list[Torrent] = []
    retries = 0
    while retries < max_retries:
        try:
            torrents = extract_torrents(scraped_results)
            print(f"Successfully extracted results in {time() - start_time:.2f} sec.")
            return torrents
        except Exception:
            retries += 1
            print(f"Failed to extract results: Attempt {retries}/{max_retries}")
    print(
        f"Exhausted all {max_retries} retries. "
        f"Returning empty list. Total time: {time() - start_time:.2f} sec."
    )
    return torrents
