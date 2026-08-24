"""Unit tests for TorrentSearchApi: search, get, cache and CLI."""

from typing import Any

import pytest

from torrent_search.wrapper import api_client as ac
from torrent_search.wrapper.models import Torrent
from torrent_search.wrapper.utils import Compress62


def _torrent(seeders: int, magnet: str, source: str = "nyaa.si") -> Torrent:
    return Torrent.format(
        filename="Show S01E01 1080p",
        size="1.2 GiB",
        seeders=seeders,
        leechers=0,
        date="2026-01-01",
        magnet_link=magnet,
        source=source,
    )


def test_available_sources() -> None:
    api = ac.TorrentSearchApi()
    assert api.available_sources() == ac.SOURCES
    assert "nyaa.si" in ac.SOURCES


def test_key_builder_normalizes_case_and_kwargs() -> None:
    positional = ac.key_builder("fn", object(), "Breaking Bad", 10)
    assert positional == ac.key_builder("fn", object(), "breaking bad", 10)
    by_kwargs = ac.key_builder("fn", object(), query="Breaking Bad", max_items=10)
    assert by_kwargs == positional


def test_extract_info_tolerates_dashes_in_ref_id() -> None:
    torrent_id = f"{Compress62.compress('breaking bad')}-10-nyaa.si-abc-def"
    query, max_items, source, ref_id = Torrent.extract_info(torrent_id)
    assert (query, max_items, source, ref_id) == (
        "breaking bad",
        10,
        "nyaa.si",
        "abc-def",
    )


@pytest.mark.asyncio
async def test_search_sorts_truncates_and_caches(monkeypatch: Any) -> None:
    async def fake_search(
        query: str, sources: list[str] | None = None
    ) -> list[Torrent]:
        return [
            _torrent(1, f"magnet:?xt=urn:btih:{'a' * 40}&dn=1"),
            _torrent(99, f"magnet:?xt=urn:btih:{'b' * 40}&dn=2"),
            _torrent(50, f"magnet:?xt=urn:btih:{'c' * 40}&dn=3"),
        ]

    monkeypatch.setattr(ac, "search_torrents", fake_search)
    api = ac.TorrentSearchApi()
    results = await api.search_torrents("unique query 42", max_items=2)
    assert len(results) == 2
    assert [t.seeders for t in results] == [99, 50]  # sorted desc
    assert results[0].id.startswith(f"{Compress62.compress('unique query 42')}-2-")
    assert api.CACHE.get(results[0].id) is not None


@pytest.mark.asyncio
async def test_get_torrent_from_cache(monkeypatch: Any) -> None:
    async def fake_search(
        query: str, sources: list[str] | None = None
    ) -> list[Torrent]:
        return [_torrent(5, f"magnet:?xt=urn:btih:{'a' * 40}&dn=1")]

    monkeypatch.setattr(ac, "search_torrents", fake_search)
    api = ac.TorrentSearchApi()
    torrents = await api.search_torrents("cached query", max_items=10)
    torrent_id = torrents[0].id
    assert await api.get_torrent(torrent_id) == torrents[0].magnet_link


@pytest.mark.asyncio
async def test_get_torrent_researches_when_missing(monkeypatch: Any) -> None:
    async def fake_search(
        query: str, sources: list[str] | None = None
    ) -> list[Torrent]:
        return [_torrent(5, f"magnet:?xt=urn:btih:{'a' * 40}&dn=1")]

    monkeypatch.setattr(ac, "search_torrents", fake_search)
    api = ac.TorrentSearchApi()
    torrents = await api.search_torrents("researched query", max_items=10)
    torrent_id = torrents[0].id
    api.CACHE.cache.clear()
    assert await api.get_torrent(torrent_id) == torrents[0].magnet_link


@pytest.mark.asyncio
async def test_get_torrent_invalid_id_returns_none() -> None:
    api = ac.TorrentSearchApi()
    assert await api.get_torrent("not-an-id") is None


@pytest.mark.asyncio
async def test_get_torrent_valid_id_but_not_found(monkeypatch: Any) -> None:
    async def fake_search(
        query: str, sources: list[str] | None = None
    ) -> list[Torrent]:
        return []

    monkeypatch.setattr(ac, "search_torrents", fake_search)
    api = ac.TorrentSearchApi()
    torrent = _torrent(5, f"magnet:?xt=urn:btih:{'a' * 40}&dn=1")
    torrent.prepend_info("vanished", 10)
    assert await api.get_torrent(torrent.id) is None


def test_exclude_sources_env(monkeypatch: Any) -> None:
    import importlib

    monkeypatch.setenv("EXCLUDE_SOURCES", "nyaa.si, eztvx.to ")
    reloaded = importlib.reload(ac)
    assert "nyaa.si" not in reloaded.SOURCES
    assert "eztvx.to" not in reloaded.SOURCES
    assert set(reloaded.EXCLUDE_SOURCES) == {"nyaa.si", "eztvx.to"}
    monkeypatch.delenv("EXCLUDE_SOURCES")
    importlib.reload(ac)  # restore without env
    assert "nyaa.si" in ac.SOURCES


@pytest.mark.asyncio
async def test_cli_with_query(monkeypatch: Any, capsys: Any) -> None:
    async def fake_search(
        query: str, sources: list[str] | None = None
    ) -> list[Torrent]:
        return [_torrent(5, f"magnet:?xt=urn:btih:{'a' * 40}&dn=1")]

    async def fake_get(torrent_id: str) -> str | None:
        return "magnet:?xt=urn:btih:aaaa"

    monkeypatch.setattr(ac, "search_torrents", fake_search)
    api = ac.TorrentSearchApi()
    monkeypatch.setattr(api, "get_torrent", fake_get)
    await api.cli("breaking bad")
    out = capsys.readouterr().out
    assert "Found Sources" in out
    assert "Result:" in out


@pytest.mark.asyncio
async def test_cli_no_results(monkeypatch: Any, capsys: Any) -> None:
    async def fake_search(
        query: str, sources: list[str] | None = None
    ) -> list[Torrent]:
        return []

    monkeypatch.setattr(ac, "search_torrents", fake_search)
    await ac.TorrentSearchApi().cli("nothing here")
    assert "No torrents found" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_cli_without_query(monkeypatch: Any, capsys: Any) -> None:
    monkeypatch.setattr(ac, "argv", ["prog"])
    await ac.TorrentSearchApi().cli()
    assert "Please provide a search query." in capsys.readouterr().out


@pytest.mark.asyncio
async def test_popular_torrents_sorts_truncates_and_caches(monkeypatch: Any) -> None:
    async def fake_popular(per_source: int = 10) -> list[Torrent]:
        calls.append(per_source)
        # Order mirrors the scraper layer, which ranks globally before returning
        return [
            _torrent(50, f"magnet:?xt=urn:btih:{'a' * 40}&dn=a", source="nyaa.si"),
            _torrent(20, f"magnet:?xt=urn:btih:{'a' * 40}&dn=b", source="nyaa.si"),
            _torrent(90, f"magnet:?xt=urn:btih:{'a' * 40}&dn=c", source="yts.mx"),
        ]

    calls: list[int] = []
    monkeypatch.setattr(ac, "scrape_popular_torrents", fake_popular)
    api = ac.TorrentSearchApi()
    results = await api.popular_torrents(per_source=2)

    assert calls == [2]
    assert len(results) == 3
    assert all(t.id.startswith(f"{Compress62.compress('')}-2-") for t in results)
    assert api.CACHE.get(results[0].id) is not None


def test_key_builder_scopes_by_function() -> None:
    async def one():
        return None

    async def two():
        return None

    assert ac.key_builder(one) != ac.key_builder(two)
    assert ac.key_builder(one) == ac.key_builder(one)
