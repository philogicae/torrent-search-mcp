from typing import Any

import pytest
from fastmcp import Client

from .mcp_server import mcp


@pytest.fixture(scope="session")
def mcp_client() -> Client[Any]:
    """Create a FastMCP client for testing."""
    return Client(mcp)


@pytest.mark.asyncio
async def test_read_resource_torrent_sources(mcp_client: Client[Any]) -> None:
    """Test reading the 'torrent_sources' resource."""
    async with mcp_client as client:
        result = await client.read_resource("data://torrent_sources")
        assert result is not None and len(result[0].text) > 8  # At least 1 source


@pytest.mark.asyncio
async def test_prepare_search_query(mcp_client: Client[Any]) -> None:
    """Test the 'prepare_search_query' tool."""
    async with mcp_client as client:
        result = await client.call_tool(
            "prepare_search_query",
            {
                "user_intent": "last episode of Breaking Bad",
                "search_query": "breaking bad s05e16",
            },
        )
        assert result is not None and len(result[0].text) > 8  # Success


@pytest.mark.asyncio
async def test_search_torrents(mcp_client: Client[Any]) -> None:
    """Test the 'search_torrents' tool."""
    async with mcp_client as client:
        result = await client.call_tool("search_torrents", {"query": "berserk"})
        assert (
            result is not None and len(result[0].text) > 32
        )  # At least 1 torrent found


@pytest.mark.asyncio
async def test_get_torrent_details(mcp_client: Client[Any]) -> None:
    """Test the 'get_torrent_details' tool."""
    async with mcp_client as client:
        result = await client.call_tool(
            "get_torrent_details",
            {"torrent_id": "t7O3z6diFKc3BneNfORT-5-nyaa.si-4ff655d4ae"},
        )
        assert result is not None and len(result[0].text) > 32  # Torrent found


@pytest.mark.asyncio
async def test_get_magnet_link(mcp_client: Client[Any]) -> None:
    """Test the 'get_magnet_link' tool."""
    async with mcp_client as client:
        result = await client.call_tool(
            "get_magnet_link",
            {"torrent_id": "t7O3z6diFKc3BneNfORT-5-yggtorrent-1268760"},
        )
        assert result is not None and len(result[0].text) > 32  # Magnet link found
