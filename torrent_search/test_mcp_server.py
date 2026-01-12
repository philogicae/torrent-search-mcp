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
            {
                "user_intent": "last episode of Breaking Bad",
                "query": "breaking bad s05e16",
            },
        )
        assert (
            result is not None and len(result.content[0].text) > 32
        )  # At least 1 torrent found


@pytest.mark.asyncio
async def test_get_torrent(mcp_client: Client[Any]) -> None:
    """Test the 'get_torrent' tool."""
    async with mcp_client as client:
        result = await client.call_tool(
            "get_torrent",
            {"torrent_id": "t7O3z6diFKc3BneNfORT-5-nyaa.si-4ff655d4ae"},
        )
        assert (
            result is not None and len(result.content[0].text) > 32
        )  # Magnet link or torrent file found
