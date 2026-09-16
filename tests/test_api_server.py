"""API server tests with a mocked search API."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from torrent_search import api_server
from torrent_search.wrapper.models import Torrent


def _torrent(magnet: str = f"magnet:?xt=urn:btih:{'a' * 40}&dn=x") -> Torrent:
    return Torrent.format(
        filename="Show S01E01 1080p",
        size="1.2 GiB",
        seeders=10,
        leechers=5,
        date="2026-01-01",
        magnet_link=magnet,
        source="nyaa.si",
    )


@pytest.fixture
def client(monkeypatch: Any) -> TestClient:
    async def fake_search(
        query: str, max_items: int | None = 10, per_source: int | None = None
    ) -> list[Torrent]:
        return [_torrent()]

    async def fake_get(torrent_id: str) -> str | None:
        return "magnet:?xt=urn:btih:aaaa&dn=x"

    monkeypatch.setattr(api_server.api_client, "search_torrents", fake_search)
    monkeypatch.setattr(api_server.api_client, "get_torrent", fake_get)
    return TestClient(api_server.app)


def test_webui_served_at_root(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Torrent Search" in response.text
    assert "__TELEGRAM_BOT_HANDLE__" not in response.text
    # UI affordances shipped with the redesign.
    for marker in (
        "loading-label",
        "- OR -",
        "Copy Prompt",
        "data-sort=name",
        "class=brand",
        "href=/",
    ):
        assert marker in response.text


def test_static_telegram_icon(client: TestClient) -> None:
    response = client.get("/static/telegram.svg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert response.text.startswith("<svg")


def test_search_torrents_endpoint(client: TestClient) -> None:
    response = client.post("/torrent/search", params={"query": "show s01e01"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["cache-control"] == "no-cache, no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["expires"] == "0"
    body = response.json()
    assert len(body) == 1
    assert body[0]["filename"] == "Show S01E01 1080p"
    assert body[0]["source"] == "nyaa.si"


def test_search_torrents_per_source_endpoint(monkeypatch: Any) -> None:
    seen: dict[str, Any] = {}

    async def fake_search(
        query: str, max_items: int | None = None, per_source: int | None = None
    ) -> list[Torrent]:
        seen.update(query=query, max_items=max_items, per_source=per_source)
        return [_torrent()]

    monkeypatch.setattr(api_server.api_client, "search_torrents", fake_search)
    client = TestClient(api_server.app)

    response = client.post("/torrent/search", params={"query": "show", "per_source": 2})
    assert response.status_code == 200
    # Spread mode: no implicit global cap, the per-source cap wins.
    assert seen == {"query": "show", "max_items": None, "per_source": 2}

    client.post("/torrent/search", params={"query": "show"})
    # Historical default stays: global cap of 20 when no per_source is given.
    assert seen == {"query": "show", "max_items": 20, "per_source": None}


def test_get_torrent_encoded_unsafe_id_stays_one_segment(monkeypatch: Any) -> None:
    torrent = Torrent.format(
        filename="Show S01E01 1080p",
        size="1.2 GiB",
        seeders=1,
        leechers=0,
        date="2026-01-01",
        magnet_link=f"magnet:?xt=urn:btih:{'a' * 40}",
        source="weird source/inner",
    )
    torrent.prepend_info("q", 5)
    assert "/" not in torrent.id

    async def fake_get(torrent_id: str) -> str | None:
        return "magnet:?xt=urn:btih:aaaa" if torrent_id == torrent.id else None

    monkeypatch.setattr(api_server.api_client, "get_torrent", fake_get)
    client = TestClient(api_server.app)
    response = client.get(f"/torrent/{torrent.id}")
    assert response.status_code == 200
    assert response.json() == "magnet:?xt=urn:btih:aaaa"


def test_get_torrent_returns_magnet(client: TestClient) -> None:
    response = client.get("/torrent/any-id")
    assert response.status_code == 200
    assert response.json() == "magnet:?xt=urn:btih:aaaa&dn=x"


def test_list_sources_endpoint() -> None:
    client = TestClient(api_server.app)
    response = client.get("/sources")
    assert response.status_code == 200
    assert "thepiratebay.org" in response.json()


def test_get_popular_torrents(monkeypatch: Any) -> None:
    async def fake_popular(per_source: int = 10) -> list[Torrent]:
        return [_torrent()][:per_source]

    monkeypatch.setattr(api_server.api_client, "popular_torrents", fake_popular)
    client = TestClient(api_server.app)

    response = client.get("/torrent/popular", params={"per_source": 5})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["cache-control"] == "no-cache, no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["expires"] == "0"
    body = response.json()
    assert len(body) == 1
    assert body[0]["filename"] == "Show S01E01 1080p"


def test_get_torrent_not_found(monkeypatch: Any) -> None:
    async def fake_get(torrent_id: str) -> str | None:
        return None

    monkeypatch.setattr(api_server.api_client, "get_torrent", fake_get)
    client = TestClient(api_server.app)
    response = client.get("/torrent/any-id")
    assert response.status_code == 404
