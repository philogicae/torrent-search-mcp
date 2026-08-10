"""FastAPI server tests with a mocked search API."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from torrent_search import fastapi_server
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
    async def fake_search(query: str, max_items: int = 10) -> list[Torrent]:
        return [_torrent()]

    async def fake_get(torrent_id: str) -> str | None:
        return "magnet:?xt=urn:btih:aaaa&dn=x"

    monkeypatch.setattr(fastapi_server.api_client, "search_torrents", fake_search)
    monkeypatch.setattr(fastapi_server.api_client, "get_torrent", fake_get)
    return TestClient(fastapi_server.app)


def test_health_check(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_search_torrents_endpoint(client: TestClient) -> None:
    response = client.post("/torrent/search", params={"query": "show s01e01"})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["filename"] == "Show S01E01 1080p"
    assert body[0]["source"] == "nyaa.si"


def test_get_torrent_returns_magnet(client: TestClient) -> None:
    response = client.get("/torrent/any-id")
    assert response.status_code == 200
    assert response.json() == "magnet:?xt=urn:btih:aaaa&dn=x"


def test_get_torrent_returns_torrent_file(monkeypatch: Any, tmp_path: Path) -> None:
    torrent_file = tmp_path / "example.torrent"
    torrent_file.write_bytes(b"mock torrent data")

    async def fake_get(torrent_id: str) -> str | None:
        return str(torrent_file)

    monkeypatch.setattr(fastapi_server.api_client, "get_torrent", fake_get)
    client = TestClient(fastapi_server.app)
    response = client.get("/torrent/any-id")
    assert response.status_code == 200
    assert response.content == b"mock torrent data"
    assert response.headers["content-type"] == "application/x-bittorrent"


def test_get_torrent_not_found(monkeypatch: Any) -> None:
    async def fake_get(torrent_id: str) -> str | None:
        return None

    monkeypatch.setattr(fastapi_server.api_client, "get_torrent", fake_get)
    client = TestClient(fastapi_server.app)
    response = client.get("/torrent/any-id")
    assert response.status_code == 404
