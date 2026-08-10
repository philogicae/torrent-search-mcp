"""Unit tests for scraper.py: registry, source dispatch and search pipeline."""

from typing import Any

import pytest
from typing_extensions import Self

from torrent_search.wrapper import scraper
from torrent_search.wrapper.parser import CSV_HEADER, SourceParser

TPB_HTML = """
<ol id="torrents" class="view-single">
<li class="list-header">junk</li>
<li>Video - Movies > Fake Movie 1080p > 2026-01-01 > magnet:?xt=urn:btih:abcdef&dn=x > 1.2 GB > 10 > 5 > uploader</li>
</ol>
"""


class FakeCrawlResult:
    def __init__(self) -> None:
        self.cleaned_html = TPB_HTML
        self.markdown = ""


class FakeCrawler:
    def __init__(self) -> None:
        self.urls: list[str] = []
        self.configs: list[Any] = []

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    async def arun(self, url: str, config: Any = None) -> FakeCrawlResult:
        self.urls.append(url)
        self.configs.append(config)
        return FakeCrawlResult()


def test_websites_registry_complete() -> None:
    assert list(scraper.WEBSITES) == [
        "thepiratebay.org",
        "nyaa.si",
        "yts.mx",
        "apibay.org",
        "eztvx.to",
        "fitgirl-repacks.site",
        "subsplease.org",
        "bittorrented.com",
        "1337x.to",
    ]
    tpb = scraper.WEBSITES["thepiratebay.org"]
    assert tpb["parsing"] == "html"
    assert "search" in tpb
    assert tpb["exclude_patterns"]
    for name, data in scraper.WEBSITES.items():
        if name != "thepiratebay.org":
            assert callable(data["parser"])


@pytest.mark.asyncio
async def test_scrape_source_parser_path() -> None:
    async def fake_parser(query: str) -> str:
        return f"{CSV_HEADER}\nfake;{query}"

    result = await scraper._scrape_source("yts.mx", {"parser": fake_parser}, "test")
    assert result == "SOURCE -> yts.mx\n" + f"{CSV_HEADER}\nfake;test"


@pytest.mark.asyncio
async def test_scrape_source_parser_failure_logs_and_returns_none(
    monkeypatch: Any, caplog: Any
) -> None:
    async def broken_parser(query: str) -> str:
        raise RuntimeError("boom")

    with caplog.at_level("WARNING", logger="Torrent Search"):
        assert (
            await scraper._scrape_source("yts.mx", {"parser": broken_parser}, "test")
            is None
        )
    assert "Error scraping yts.mx" in caplog.text
    assert "boom" in caplog.text


@pytest.mark.asyncio
async def test_scrape_source_crawler_path(monkeypatch: Any) -> None:
    monkeypatch.setattr(scraper, "crawler", FakeCrawler())
    data: dict[str, str | list[str] | SourceParser] = {
        "search": "https://thepiratebay.org/search.php?q={query}&cat=0",
        "parsing": "html",
        "exclude_patterns": [
            "some_texts",
            "local_links",
            "single_angle_bracket",
            "html_tags",
        ],
    }
    result = await scraper._scrape_source("thepiratebay.org", data, "fake movie")
    assert result is not None and result.startswith("SOURCE -> thepiratebay.org")
    assert "Fake Movie 1080p" in result


def _fake_parser(text: str) -> Any:
    async def fake(query: str = "") -> str:
        return text

    return fake


@pytest.mark.asyncio
async def test_scrape_torrents_runs_all_sources_in_parallel(monkeypatch: Any) -> None:
    monkeypatch.setattr(scraper, "crawler", FakeCrawler())
    monkeypatch.setattr(scraper, "ensure_trackers", _fake_parser(""))

    async def fake_parser(query: str) -> str:
        return f"{CSV_HEADER}\nresult;{query}"

    for name, data in scraper.WEBSITES.items():
        if name != "thepiratebay.org":
            monkeypatch.setitem(data, "parser", fake_parser)

    results = await scraper.scrape_torrents("test")
    assert len(results) == 9
    sources = {r.split("\n", 1)[0].removeprefix("SOURCE -> ") for r in results}
    assert sources == set(scraper.WEBSITES)


@pytest.mark.asyncio
async def test_scrape_torrents_filters_sources(monkeypatch: Any) -> None:
    monkeypatch.setattr(scraper, "crawler", FakeCrawler())
    monkeypatch.setattr(scraper, "ensure_trackers", _fake_parser(""))

    async def fake_parser(query: str) -> str:
        return f"{CSV_HEADER}\nresult;{query}"

    monkeypatch.setitem(scraper.WEBSITES["nyaa.si"], "parser", fake_parser)
    results = await scraper.scrape_torrents("test", sources=["nyaa.si"])
    assert len(results) == 1
    assert results[0].startswith("SOURCE -> nyaa.si")


@pytest.mark.asyncio
async def test_search_torrents_success(monkeypatch: Any) -> None:
    text = f"SOURCE -> nyaa.si\n{CSV_HEADER}\nShow;Anime;1 GB;5;2;10;2026-01-01;magnet:?xt=urn:btih:abcdef&dn=x"

    async def fake_scrape(query: str, sources: list[str] | None = None) -> list[str]:
        return [text]

    monkeypatch.setattr(scraper, "scrape_torrents", fake_scrape)
    torrents = await scraper.search_torrents("show")
    assert len(torrents) == 1
    assert torrents[0].filename == "Show"
    assert torrents[0].source == "nyaa.si"


@pytest.mark.asyncio
async def test_search_torrents_extraction_failure_returns_empty(
    monkeypatch: Any, caplog: Any
) -> None:
    async def fake_scrape(query: str, sources: list[str] | None = None) -> list[str]:
        return ["SOURCE -> nyaa.si\njunk"]

    monkeypatch.setattr(scraper, "scrape_torrents", fake_scrape)
    monkeypatch.setattr(scraper, "extract_torrents", _raise_runtime_error)
    with caplog.at_level("WARNING", logger="Torrent Search"):
        assert await scraper.search_torrents("show") == []
    assert "Failed to extract results" in caplog.text


def _raise_runtime_error(_texts: list[str]) -> list[Any]:
    raise RuntimeError("parse failure")
