from typing import Any

import pytest
from fastmcp import Client

from .mcp_server import mcp


@pytest.fixture(scope="session")
def mcp_client() -> Client[Any]:
    """Create a FastMCP client for testing."""
    return Client(mcp)


@pytest.mark.asyncio
async def test_search_torrents(mcp_client: Client[Any]) -> None:
    """Test the 'search_torrents' tool."""
    async with mcp_client as client:
        result = await client.call_tool(
            "search_torrents",
            {"user_intent": "complete Breaking Bad series", "query": "breaking bad"},
        )
        assert (
            result is not None and len(result.content[0].text) > 32
        )  # At least 1 torrent found


@pytest.mark.asyncio
async def test_get_torrent_thepiratebay(mcp_client: Client[Any]) -> None:
    """Test the 'get_torrent' tool for ThePirateBay."""
    async with mcp_client as client:
        result = await client.call_tool(
            "get_torrent",
            {"torrent_id": "DLeDVjR9sx2X1eDdRe5-10-thepiratebay.org-315fa287d5"},
        )
        assert (
            result is not None and len(result.content[0].text) > 32
        )  # Magnet link found


@pytest.mark.asyncio
async def test_get_torrent_nyaa(mcp_client: Client[Any]) -> None:
    """Test the 'get_torrent' tool for Nyaa."""
    async with mcp_client as client:
        result = await client.call_tool(
            "get_torrent",
            {"torrent_id": "DLeDVjR9sx2X1eDdRe5-10-nyaa.si-62fc3d3c8c"},
        )
        assert (
            result is not None and len(result.content[0].text) > 32
        )  # Magnet link found
