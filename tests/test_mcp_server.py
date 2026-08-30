"""MCP server tests: tools and resources with a mocked search API."""

from typing import Any

import httpx
import pytest
from fastmcp import Client

from torrent_search import mcp_server
from torrent_search.wrapper.models import Torrent


def _torrent(
    magnet: str = f"magnet:?xt=urn:btih:{'a' * 40}&dn=x",
    page_url: str | None = "https://nyaa.si/view/123",
) -> Torrent:
    return Torrent.format(
        filename="Show S01E01 1080p",
        category="Video",
        size="1.2 GiB",
        seeders=10,
        leechers=5,
        downloads="100",
        date="2026-01-01",
        magnet_link=magnet,
        page_url=page_url,
        source="nyaa.si",
    )


@pytest.fixture
def mcp_client() -> Client[Any]:
    return Client(mcp_server.mcp)


async def _fake_search(torrents: list[Torrent]) -> Any:
    async def fake(query: str, max_items: int = 10) -> list[Torrent]:
        return torrents

    return fake


async def _fake_popular(torrents: list[Torrent]) -> Any:
    async def fake(per_source: int = 10) -> list[Torrent]:
        return torrents

    return fake


@pytest.mark.asyncio
async def test_available_sources_tool() -> None:
    result = await mcp_server.available_sources()
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
    assert "https://nyaa.si/view/123" in text  # page URL included


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
    assert "nyaa.si/view" in text  # source page URL is still useful


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


@pytest.mark.asyncio
async def test_popular_torrents_tool(monkeypatch: Any, mcp_client: Client[Any]) -> None:
    torrent = _torrent()
    monkeypatch.setattr(mcp_server, "INCLUDE_LINKS", True)
    monkeypatch.setattr(
        mcp_server.torrent_search_api,
        "popular_torrents",
        await _fake_popular([torrent]),
    )
    async with mcp_client as client:
        result = await client.call_tool("popular_torrents", {})
    assert "magnet:?xt=urn:btih" in result.content[0].text


@pytest.mark.asyncio
async def test_popular_torrents_no_results(monkeypatch: Any) -> None:
    async def fake(per_source: int = 10) -> list[Torrent]:
        return []

    monkeypatch.setattr(mcp_server.torrent_search_api, "popular_torrents", fake)
    assert await mcp_server.popular_torrents() == "No torrents found"


@pytest.mark.asyncio
async def test_popular_torrents_groups_by_source(monkeypatch: Any) -> None:
    nyaa = _torrent(magnet=f"magnet:?xt=urn:btih:{'a' * 40}&dn=n")
    yts = _torrent(magnet=f"magnet:?xt=urn:btih:{'b' * 40}&dn=y")
    nyaa = nyaa.model_copy(update={"source": "nyaa.si"})
    yts = yts.model_copy(update={"source": "yts.vg"})
    monkeypatch.setattr(
        mcp_server.torrent_search_api,
        "popular_torrents",
        await _fake_popular([nyaa, yts]),
    )
    text = await mcp_server.popular_torrents()
    yts_pos, nyaa_pos = text.index("== yts.vg =="), text.index("== nyaa.si ==")
    assert yts_pos < nyaa_pos  # traffic ranking: YTS before nyaa
    assert text.count("== ") == 2


def test_format_torrents_by_source_orders_unknown_last() -> None:
    obscure = _torrent(magnet=f"magnet:?xt=urn:btih:{'c' * 40}&dn=o")
    yts = _torrent(magnet=f"magnet:?xt=urn:btih:{'b' * 40}&dn=y")
    obscure = obscure.model_copy(update={"source": "zzz-unknown.example"})
    yts = yts.model_copy(update={"source": "yts.vg"})
    text = mcp_server._format_torrents([obscure, yts], by_source=True)
    assert text.index("== yts.vg ==") < text.index("== zzz-unknown.example ==")


@pytest.mark.asyncio
async def test_all_tools_exposed(mcp_client: Client[Any]) -> None:
    async with mcp_client:
        tools = await mcp_client.list_tools()
    assert {t.name for t in tools} >= {
        "search_torrents",
        "popular_torrents",
        "get_torrent",
        "available_sources",
        "authorize_webapp",
        "torrent_webapp",
    }


@pytest.mark.asyncio
async def test_remote_api_mode_proxies_tools(
    monkeypatch: Any, mcp_client: Client[Any]
) -> None:
    torrent = _torrent()
    monkeypatch.setattr(mcp_server, "API_BASE_URL", "http://test")

    async def fake_json(path: str, params: dict[str, str] | None = None) -> Any:
        if path == "/sources":
            return mcp_server.SOURCES
        return [torrent.model_dump()]

    monkeypatch.setattr(mcp_server, "_api_get_json", fake_json)
    monkeypatch.setattr(mcp_server, "_api_post_json", fake_json)
    async with mcp_client as client:
        search = await client.call_tool(
            "search_torrents",
            {"user_intent": "intent", "query": "show"},
        )
        popular = await client.call_tool("popular_torrents", {})
        sources = await client.call_tool("available_sources", {})
    assert "Show S01E01 1080p" in search.content[0].text
    assert "Show S01E01 1080p" in popular.content[0].text
    assert "nyaa.si" in sources.content[0].text


@pytest.mark.asyncio
async def test_remote_api_mode_get_torrent(monkeypatch: Any) -> None:
    monkeypatch.setattr(mcp_server, "API_BASE_URL", "http://test")

    async def fake_text(path: str) -> str:
        return "magnet:?xt=urn:btih:abc"

    monkeypatch.setattr(mcp_server, "_api_get_text", fake_text)
    assert await mcp_server.get_torrent("some-id") == "magnet:?xt=urn:btih:abc"


@pytest.mark.asyncio
async def test_remote_api_mode_get_torrent_404(monkeypatch: Any) -> None:
    monkeypatch.setattr(mcp_server, "API_BASE_URL", "http://test")

    async def fake_text(path: str) -> str:
        request = httpx.Request("GET", "http://test/torrent/x")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("404", request=request, response=response)

    monkeypatch.setattr(mcp_server, "_api_get_text", fake_text)
    assert await mcp_server.get_torrent("missing") == "Torrent not found"


@pytest.mark.asyncio
async def test_api_client_lazy_singleton(monkeypatch: Any) -> None:
    monkeypatch.setattr(mcp_server, "_api_client", None)
    client = mcp_server._api()
    assert client is mcp_server._api()  # built once, reused afterwards
    await client.aclose()


@pytest.mark.asyncio
async def test_remote_api_real_transport(monkeypatch: Any) -> None:
    """Exercise the real _api client helpers against a mocked transport."""
    torrent = _torrent()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/sources":
            return httpx.Response(200, json=mcp_server.SOURCES)
        if request.url.path == "/torrent/popular":
            return httpx.Response(200, json=[torrent.model_dump()])
        if request.url.path == "/torrent/search":
            assert request.method == "POST", "search must use POST"
            return httpx.Response(200, json=[torrent.model_dump()])
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        mcp_server,
        "_api_client",
        httpx.AsyncClient(transport=transport, base_url="http://test"),
    )
    monkeypatch.setattr(mcp_server, "API_BASE_URL", "http://test")

    assert await mcp_server._api_get_json("/sources") == mcp_server.SOURCES
    assert (await mcp_server._fetch_torrents("/torrent/popular", {}))[0].filename
    assert (
        await mcp_server._fetch_torrents("/torrent/search", {"query": "x"}, post=True)
    )[0].filename
    assert isinstance(await mcp_server._api_get_text("/sources"), str)
    with pytest.raises(httpx.HTTPStatusError):
        await mcp_server._api_get_text("/torrent/unknown")
    # get_torrent surfaces non-404 API errors to the caller
    with pytest.raises(httpx.HTTPStatusError):
        await mcp_server.get_torrent("any-id")

    # The shared client is reused across calls
    assert mcp_server._api() is mcp_server._api_client


@pytest.mark.asyncio
async def test_authorize_webapp_disabled(monkeypatch: Any) -> None:
    monkeypatch.delenv("TORRENT_SEARCH_API_KEY", raising=False)
    result = await mcp_server.authorize_webapp("some-code", "12345")
    assert "disabled" in result


@pytest.mark.asyncio
async def test_authorize_webapp_requires_api_url(monkeypatch: Any) -> None:
    monkeypatch.setenv("TORRENT_SEARCH_API_KEY", "s")
    result = await mcp_server.authorize_webapp("some-code", "12345")
    assert "TORRENT_SEARCH_API_URL" in result


@pytest.mark.asyncio
async def test_authorize_webapp_remote(monkeypatch: Any) -> None:
    monkeypatch.setenv("TORRENT_SEARCH_API_KEY", "reg-secret")
    monkeypatch.setattr(mcp_server, "API_BASE_URL", "http://test")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer reg-secret"
        code = request.url.params["code"]
        assert request.url.params["chat_id"] == "12345"
        if code == "good":
            return httpx.Response(200, json={"status": "approved"})
        if code == "stale":
            return httpx.Response(404, json={"detail": "unknown"})
        return httpx.Response(401, json={"detail": "bad secret"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        mcp_server,
        "_api_client",
        httpx.AsyncClient(transport=transport, base_url="http://test"),
    )
    assert "Access granted" in await mcp_server.authorize_webapp("good", "12345")
    assert "Unknown or expired" in await mcp_server.authorize_webapp("stale", "12345")
    assert "does not match" in await mcp_server.authorize_webapp("other", "12345")


@pytest.mark.asyncio
async def test_torrent_webapp_tool(monkeypatch: Any) -> None:
    monkeypatch.delenv("WEBUI_URL", raising=False)
    assert "WEBUI_URL" in await mcp_server.torrent_webapp()
    monkeypatch.setenv("WEBUI_URL", "http://web.local:8000/")
    text = await mcp_server.torrent_webapp()
    assert "http://web.local:8000" in text
    assert "authorize_webapp" in text
