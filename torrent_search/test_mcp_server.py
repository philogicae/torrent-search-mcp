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
        assert result is not None and result[0].text


@pytest.mark.asyncio
async def test_search_torrents(mcp_client: Client[Any]) -> None:
    """Test the 'search_torrents' tool."""
    async with mcp_client as client:
        result = await client.call_tool("search_torrents", {"query": "berserk"})
        assert result is not None and result[0].text


@pytest.mark.asyncio
async def test_get_ygg_torrent_details_with_magnet(mcp_client: Client[Any]) -> None:
    """Test the 'get_ygg_torrent_details' tool with magnet link request."""
    async with mcp_client as client:
        result = await client.call_tool(
            "get_ygg_torrent_details", {"torrent_id": 1268760, "with_magnet_link": True}
        )
        assert result is not None and result[0].text


@pytest.mark.asyncio
async def test_get_ygg_magnet_link(mcp_client: Client[Any]) -> None:
    """Test the 'get_ygg_magnet_link' tool."""
    async with mcp_client as client:
        result = await client.call_tool("get_ygg_magnet_link", {"torrent_id": 1268760})
        assert result is not None and result[0].text
