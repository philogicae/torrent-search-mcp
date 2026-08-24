"""Unit tests for scraper.py: registry, source dispatch and search pipeline."""

import asyncio
import time
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
        self.ready = True
        self.urls: list[str] = []
        self.configs: list[Any] = []
        self.closed = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    async def start(self) -> None:
        self.ready = True

    async def close(self) -> None:
        self.ready = False
        self.closed = True

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
        "uindex.org",
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
    assert len(results) == 10
    sources = {r.split("\n", 1)[0].removeprefix("SOURCE -> ") for r in results}
    assert sources == set(scraper.WEBSITES)


@pytest.mark.asyncio
async def test_popular_torrents_per_source(monkeypatch: Any) -> None:
    async def fake_popular_listing() -> str:
        rows = "\n".join(
            f"Name{i};Anime;1 GB;{100 - i};{i};10;2026-01-01;magnet:?xt=urn:btih:{'a' * 40}&dn=x"
            for i in range(5)
        )
        return f"{CSV_HEADER}\n{rows}"

    monkeypatch.setattr(scraper, "ensure_trackers", _fake_parser(""))
    monkeypatch.setattr(
        scraper,
        "POPULAR_SOURCES",
        {"nyaa.si": lambda: fake_popular_listing()},
    )

    torrents = await scraper.popular_torrents(per_source=3)
    assert len(torrents) == 3
    assert [t.seeders for t in torrents] == [100, 99, 98]


@pytest.mark.asyncio
async def test_popular_torrents_skips_failing_source(monkeypatch: Any) -> None:
    def broken() -> Any:
        raise RuntimeError("down")

    async def ok() -> str:
        return f"{CSV_HEADER}\nGood;Anime;1 GB;7;2;10;2026-01-01;magnet:?xt=urn:btih:{'a' * 40}&dn=x"

    monkeypatch.setattr(scraper, "ensure_trackers", _fake_parser(""))
    monkeypatch.setattr(scraper, "POPULAR_SOURCES", {"bad.example": broken, "ok": ok})
    assert [t.filename for t in await scraper.popular_torrents()] == ["Good"]


def test_schedule_crawler_shutdown_disabled(monkeypatch: Any) -> None:
    monkeypatch.setattr(scraper, "CRAWLER_IDLE_TIMEOUT", 0)
    scraper._schedule_crawler_shutdown()
    assert scraper._crawler_idle_timer is None


@pytest.mark.asyncio
async def test_schedule_crawler_shutdown_rearms(monkeypatch: Any) -> None:
    monkeypatch.setattr(scraper, "CRAWLER_IDLE_TIMEOUT", 60)
    scraper._schedule_crawler_shutdown()
    first = scraper._crawler_idle_timer
    scraper._schedule_crawler_shutdown()
    # Old timer must no longer be the armed one
    assert scraper._crawler_idle_timer is not None
    assert scraper._crawler_idle_timer is not first


@pytest.mark.asyncio
async def test_popular_torrents_skips_unparsable_listing(monkeypatch: Any) -> None:
    async def garbage() -> str:
        return ""  # no header line -> extraction raises for this source

    async def ok() -> str:
        return f"{CSV_HEADER}\nGood;Anime;1 GB;7;2;10;2026-01-01;magnet:?xt=urn:btih:{'a' * 40}&dn=x"

    monkeypatch.setattr(scraper, "ensure_trackers", _fake_parser(""))
    monkeypatch.setattr(scraper, "POPULAR_SOURCES", {"bad.example": garbage, "ok": ok})
    assert [t.filename for t in await scraper.popular_torrents()] == ["Good"]


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


@pytest.mark.asyncio
async def test_ensure_crawler_starts_once_under_concurrency(
    monkeypatch: Any,
) -> None:
    class ColdCrawler(FakeCrawler):
        def __init__(self) -> None:
            super().__init__()
            self.ready = False
            self.started = 0

        async def start(self) -> None:
            self.started += 1
            self.ready = True

    cold = ColdCrawler()
    monkeypatch.setattr(scraper, "crawler", cold)
    await asyncio.gather(
        scraper._ensure_crawler_started(), scraper._ensure_crawler_started()
    )
    assert cold.started == 1
    assert cold.ready


@pytest.mark.asyncio
async def test_idle_crawler_shuts_down_after_timeout(monkeypatch: Any) -> None:
    fake = FakeCrawler()
    monkeypatch.setattr(scraper, "crawler", fake)
    monkeypatch.setattr(scraper, "CRAWLER_IDLE_TIMEOUT", 0.01)
    monkeypatch.setattr(scraper, "_active_scrapes", 0)
    monkeypatch.setattr(scraper, "_crawler_last_used", time.monotonic() - 30)

    await scraper._close_idle_crawler()

    assert fake.closed
    assert not fake.ready


@pytest.mark.asyncio
async def test_idle_crawler_skips_when_scrape_in_flight(monkeypatch: Any) -> None:
    fake = FakeCrawler()
    monkeypatch.setattr(scraper, "crawler", fake)
    monkeypatch.setattr(scraper, "CRAWLER_IDLE_TIMEOUT", 0.01)
    monkeypatch.setattr(scraper, "_active_scrapes", 1)
    monkeypatch.setattr(scraper, "_crawler_last_used", time.monotonic() - 30)

    await scraper._close_idle_crawler()

    assert not fake.closed
    assert fake.ready


@pytest.mark.asyncio
async def test_idle_crawler_skips_when_recently_used(monkeypatch: Any) -> None:
    fake = FakeCrawler()
    monkeypatch.setattr(scraper, "crawler", fake)
    monkeypatch.setattr(scraper, "CRAWLER_IDLE_TIMEOUT", 0.05)
    monkeypatch.setattr(scraper, "_active_scrapes", 0)
    monkeypatch.setattr(scraper, "_crawler_last_used", time.monotonic())

    async def touch() -> None:
        # A search finishing mid-window postpones the shutdown.
        await asyncio.sleep(0.02)
        scraper._crawler_last_used = time.monotonic()

    await asyncio.gather(touch(), scraper._close_idle_crawler())

    assert not fake.closed


def _raise_runtime_error(_texts: list[str]) -> list[Any]:
    raise RuntimeError("parse failure")
