import pytest
from fastmcp import Client

from .mcp_server import mcp


@pytest.mark.asyncio
async def test_search_torrents():
    """Test the 'search_torrents' tool."""
    async with Client(mcp) as client:
        result = await client.call_tool(
            "search_torrents", {"query": "berserk", "limit": 3}
        )
        assert result is not None and result[0].text


@pytest.mark.asyncio
async def test_get_torrent_details_with_magnet():
    """Test the 'get_torrent_details' tool with magnet link request."""
    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_torrent_details", {"torrent_id": 1268760, "with_magnet_link": True}
        )
        assert result is not None and result[0].text


@pytest.mark.asyncio
async def test_get_magnet_link():
    """Test the 'get_magnet_link' tool."""
    async with Client(mcp) as client:
        result = await client.call_tool("get_magnet_link", {"torrent_id": 1268760})
        assert result is not None and result[0].text
