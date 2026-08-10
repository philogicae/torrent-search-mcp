"""MCP server tests: tools and resources with a mocked search API."""

from typing import Any

import pytest
from fastmcp import Client

from torrent_search import mcp_server
from torrent_search.wrapper.models import Torrent


def _torrent(magnet: str = f"magnet:?xt=urn:btih:{'a' * 40}&dn=x") -> Torrent:
    return Torrent.format(
        filename="Show S01E01 1080p",
        category="Video",
        size="1.2 GiB",
        seeders=10,
        leechers=5,
        downloads="100",
        date="2026-01-01",
        magnet_link=magnet,
        source="nyaa.si",
    )


@pytest.fixture
def mcp_client() -> Client[Any]:
    return Client(mcp_server.mcp)


async def _fake_search(torrents: list[Torrent]) -> Any:
    async def fake(query: str, max_items: int = 10) -> list[Torrent]:
        return torrents

    return fake


@pytest.mark.asyncio
async def test_available_sources_resource() -> None:
    result = mcp_server.available_sources()
    assert result == mcp_server.SOURCES
    assert "nyaa.si" in result


@pytest.mark.asyncio
async def test_search_torrents_with_links(
    monkeypatch: Any, mcp_client: Client[Any]
) -> None:
    torrent = _torrent()
    monkeypatch.setattr(
        mcp_server.torrent_search_api, "search_torrents", await _fake_search([torrent])
    )
    monkeypatch.setattr(mcp_server, "INCLUDE_LINKS", True)

    async with mcp_client as client:
        result = await client.call_tool(
            "search_torrents",
            {"user_intent": "get the show", "query": "show s01e01"},
        )
    text = result.content[0].text
    assert "Show S01E01 1080p" in text
    assert "magnet:?xt=urn:btih" in text  # links included


@pytest.mark.asyncio
async def test_search_torrents_strips_links(
    monkeypatch: Any, mcp_client: Client[Any]
) -> None:
    torrent = _torrent()
    monkeypatch.setattr(
        mcp_server.torrent_search_api, "search_torrents", await _fake_search([torrent])
    )
    monkeypatch.setattr(mcp_server, "INCLUDE_LINKS", False)

    async with mcp_client as client:
        result = await client.call_tool(
            "search_torrents",
            {"user_intent": "get the show", "query": "show s01e01"},
        )
    text = result.content[0].text
    assert "Show S01E01 1080p" in text
    assert "magnet:" not in text  # links stripped to save tokens


@pytest.mark.asyncio
async def test_search_torrents_no_results(
    monkeypatch: Any, mcp_client: Client[Any]
) -> None:
    monkeypatch.setattr(
        mcp_server.torrent_search_api, "search_torrents", await _fake_search([])
    )

    async with mcp_client as client:
        result = await client.call_tool(
            "search_torrents",
            {"user_intent": "get the show", "query": "show"},
        )
    assert result.content[0].text == "No torrents found"


@pytest.mark.asyncio
async def test_get_torrent_found(monkeypatch: Any, mcp_client: Client[Any]) -> None:
    async def fake_get(torrent_id: str) -> str | None:
        return "magnet:?xt=urn:btih:aaaa&dn=x"

    monkeypatch.setattr(mcp_server.torrent_search_api, "get_torrent", fake_get)
    async with mcp_client as client:
        result = await client.call_tool("get_torrent", {"torrent_id": "any-id"})
    assert "magnet:?xt=urn:btih" in result.content[0].text


@pytest.mark.asyncio
async def test_get_torrent_not_found(monkeypatch: Any, mcp_client: Client[Any]) -> None:
    async def fake_get(torrent_id: str) -> str | None:
        return None

    monkeypatch.setattr(mcp_server.torrent_search_api, "get_torrent", fake_get)
    async with mcp_client as client:
        result = await client.call_tool("get_torrent", {"torrent_id": "any-id"})
    assert result.content[0].text == "Torrent not found"
