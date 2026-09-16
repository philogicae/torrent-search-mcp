"""Unit tests for scraper.py: registry, source dispatch and search pipeline."""

import asyncio
from typing import Any

import pytest

from torrent_search.wrapper import scraper
from torrent_search.wrapper.parser import CSV_HEADER


def test_websites_registry_complete() -> None:
    assert list(scraper.WEBSITES) == [
        "nyaa.si",
        "yts.mx",
        "apibay.org",
        "eztvx.to",
        "fitgirl-repacks.site",
        "subsplease.org",
        "uindex.org",
        "1337x.to",
    ]
    for parser_fn in scraper.WEBSITES.values():
        assert callable(parser_fn)


@pytest.mark.asyncio
async def test_scrape_source_parser_path() -> None:
    async def fake_parser(query: str) -> str:
        return f"{CSV_HEADER}\nfake;{query}"

    result = await scraper._scrape_source("yts.mx", fake_parser, "test")
    assert result == "SOURCE -> yts.mx\n" + f"{CSV_HEADER}\nfake;test"


@pytest.mark.asyncio
async def test_scrape_source_parser_failure_logs_and_returns_none(
    monkeypatch: Any, caplog: Any
) -> None:
    async def broken_parser(query: str) -> str:
        raise RuntimeError("boom")

    with caplog.at_level("WARNING", logger="Torrent Search"):
        assert await scraper._scrape_source("yts.mx", broken_parser, "test") is None
    assert "Error scraping yts.mx" in caplog.text
    assert "boom" in caplog.text


@pytest.mark.asyncio
async def test_scrape_source_timeout_cuts_slow_source(monkeypatch: Any) -> None:
    monkeypatch.setattr(scraper, "SOURCE_TIMEOUT", 0.01)

    async def slow_parser(query: str) -> str:
        await asyncio.sleep(5)
        return f"{CSV_HEADER}\nfake;{query}"

    assert await scraper._scrape_source("yts.mx", slow_parser, "test") is None


def _fake_parser(text: str) -> Any:
    async def fake(query: str = "") -> str:
        return text

    return fake


@pytest.mark.asyncio
async def test_scrape_torrents_runs_all_sources_in_parallel(monkeypatch: Any) -> None:
    monkeypatch.setattr(scraper, "ensure_trackers", _fake_parser(""))

    async def fake_parser(query: str) -> str:
        return f"{CSV_HEADER}\nresult;{query}"

    for name in scraper.WEBSITES:
        monkeypatch.setitem(scraper.WEBSITES, name, fake_parser)

    results = await scraper.scrape_torrents("test")
    assert len(results) == len(scraper.WEBSITES)
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
        {"nyaa.si": lambda _: fake_popular_listing()},
    )

    torrents = await scraper.popular_torrents(per_source=3)
    assert len(torrents) == 3
    assert [t.seeders for t in torrents] == [100, 99, 98]


@pytest.mark.asyncio
async def test_popular_torrents_default_keeps_everything(monkeypatch: Any) -> None:
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
        {"nyaa.si": lambda _: fake_popular_listing()},
    )

    torrents = await scraper.popular_torrents()
    assert [t.seeders for t in torrents] == [100, 99, 98, 97, 96]


@pytest.mark.asyncio
async def test_popular_torrents_skips_failing_source(monkeypatch: Any) -> None:
    def broken(_: int | None) -> Any:
        raise RuntimeError("boom")

    async def ok(_: int | None) -> str:
        return f"{CSV_HEADER}\nGood;Anime;1 GB;7;2;10;2026-01-01;magnet:?xt=urn:btih:{'a' * 40}&dn=x"

    monkeypatch.setattr(scraper, "ensure_trackers", _fake_parser(""))
    monkeypatch.setattr(scraper, "POPULAR_SOURCES", {"bad.example": broken, "ok": ok})
    assert [t.filename for t in await scraper.popular_torrents()] == ["Good"]


@pytest.mark.asyncio
async def test_popular_torrents_skips_unparsable_listing(monkeypatch: Any) -> None:
    async def garbage(_: int | None) -> str:
        return ""  # no header line -> extraction raises for this source

    async def ok(_: int | None) -> str:
        return f"{CSV_HEADER}\nGood;Anime;1 GB;7;2;10;2026-01-01;magnet:?xt=urn:btih:{'a' * 40}&dn=x"

    monkeypatch.setattr(scraper, "ensure_trackers", _fake_parser(""))
    monkeypatch.setattr(scraper, "POPULAR_SOURCES", {"bad.example": garbage, "ok": ok})
    assert [t.filename for t in await scraper.popular_torrents()] == ["Good"]


@pytest.mark.asyncio
async def test_popular_source_cache_hit_avoids_refetch() -> None:
    calls: list[int | None] = []

    async def fetch(per: int | None) -> str:
        calls.append(per)
        return f"{CSV_HEADER}\nA;Anime;1 GB;9;0;0;2026-01-01;magnet:?xt=urn:btih:{'a' * 40}&dn=x"

    first = await scraper._popular_source("s.example", fetch, 5)
    second = await scraper._popular_source("s.example", fetch, 5)
    assert first == second
    assert calls == [5]


@pytest.mark.asyncio
async def test_popular_source_larger_request_bypasses_smaller_cache() -> None:
    calls: list[int | None] = []

    async def fetch(per: int | None) -> str:
        calls.append(per)
        return f"{CSV_HEADER}\nA;Anime;1 GB;9;0;0;2026-01-01;magnet:?xt=urn:btih:{'a' * 40}&dn=x"

    await scraper._popular_source("s.example", fetch, 5)
    await scraper._popular_source("s.example", fetch, None)
    assert calls == [5, None]


@pytest.mark.asyncio
async def test_popular_source_full_cache_serves_smaller_requests() -> None:
    calls: list[int | None] = []

    async def fetch(per: int | None) -> str:
        calls.append(per)
        return f"{CSV_HEADER}\nA;Anime;1 GB;9;0;0;2026-01-01;magnet:?xt=urn:btih:{'a' * 40}&dn=x"

    first = await scraper._popular_source("s.example", fetch, None)
    second = await scraper._popular_source("s.example", fetch, 3)
    assert first == second
    assert calls == [None]


@pytest.mark.asyncio
async def test_popular_source_serves_stale_and_refreshes_in_background() -> None:
    async def first_fetch(per: int | None) -> str:
        return "old listing"

    await scraper._popular_source("s.example", first_fetch, 5)
    scraper._popular_cache["s.example"] = (0.0, 5, "SOURCE -> s.example\nstale")

    refreshed: list[int | None] = []

    async def fresh_fetch(per: int | None) -> str:
        refreshed.append(per)
        return "fresh listing"

    out = await scraper._popular_source("s.example", fresh_fetch, 5)
    assert out is not None and "stale" in out
    await scraper._popular_refreshing["s.example"]
    assert refreshed == [5]
    assert "fresh listing" in scraper._popular_cache["s.example"][2]


@pytest.mark.asyncio
async def test_popular_refresh_keeps_better_coverage() -> None:
    scraper._popular_cache["s.example"] = (0.0, None, "full listing")

    async def fetch(per: int | None) -> str:
        return "small listing"

    await scraper._refresh_popular("s.example", fetch, 5)
    assert scraper._popular_cache["s.example"][2] == "full listing"


@pytest.mark.asyncio
async def test_popular_torrents_reuses_fresh_sources(monkeypatch: Any) -> None:
    calls: list[int | None] = []

    async def listing(per: int | None) -> str:
        calls.append(per)
        return f"{CSV_HEADER}\nGood;Anime;1 GB;7;2;10;2026-01-01;magnet:?xt=urn:btih:{'a' * 40}&dn=x"

    monkeypatch.setattr(scraper, "ensure_trackers", _fake_parser(""))
    monkeypatch.setattr(scraper, "POPULAR_SOURCES", {"ok": listing})
    assert [t.filename for t in await scraper.popular_torrents(per_source=5)] == [
        "Good"
    ]
    assert [t.filename for t in await scraper.popular_torrents(per_source=5)] == [
        "Good"
    ]
    assert calls == [5]  # second call served from the per-source cache


@pytest.mark.asyncio
async def test_scrape_torrents_filters_sources(monkeypatch: Any) -> None:
    monkeypatch.setattr(scraper, "ensure_trackers", _fake_parser(""))

    async def fake_parser(query: str) -> str:
        return f"{CSV_HEADER}\nresult;{query}"

    monkeypatch.setitem(scraper.WEBSITES, "nyaa.si", fake_parser)
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
