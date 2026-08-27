from collections.abc import Callable, Iterator
from typing import Any

import pytest

from torrent_search import api_server
from torrent_search.wrapper import parser
from torrent_search.wrapper.models import Torrent


@pytest.fixture(autouse=True)
def hermetic_env(monkeypatch: Any) -> None:
    """Ambient .env (auto-loaded by uv run) must not flip module constants."""
    monkeypatch.setattr(api_server, "_PRUNE_MAGNET_LINKS", False)
    monkeypatch.setattr(api_server, "_TELEGRAM_BOT_HANDLE", None)
    monkeypatch.setattr(api_server, "_TELEGRAM_BOT_TOKEN", None)
    monkeypatch.setattr(api_server, "_TELEGRAM_AGENT_NAME", None)
    monkeypatch.setattr(api_server, "_TELEGRAM_MSG_FORWARD", None)
    monkeypatch.setattr(api_server, "_AGENT_RELAY_URL", None)
    monkeypatch.setattr(api_server, "_AGENT_RELAY_TOKEN", None)
    monkeypatch.setattr(api_server, "_AGENT_MODE", False)


@pytest.fixture(autouse=True)
def reset_parser_state() -> Iterator[None]:
    """Keep parser and scraper module globals stable across tests."""
    parser._trackers = list(parser.TRACKERS)
    parser._trackers_loaded = False
    yield
    parser._trackers = list(parser.TRACKERS)
    parser._trackers_loaded = False


@pytest.fixture(autouse=True)
def force_standalone_mcp(monkeypatch: Any) -> None:
    """Keep MCP tools standalone unless a test opts into remote-API mode."""
    monkeypatch.delenv("TORRENT_SEARCH_API_URL", raising=False)


@pytest.fixture
def make_torrent() -> Callable[..., Torrent]:
    def _make(source: str = "nyaa.si", **overrides: Any) -> Torrent:
        data = {
            "filename": "Show S01E01 1080p",
            "category": "Video",
            "size": "1.2 GiB",
            "seeders": 10,
            "leechers": 5,
            "downloads": "100",
            "date": "2026-01-01",
            "magnet_link": f"magnet:?xt=urn:btih:{'a' * 40}&dn=x",
        }
        data.update(overrides)
        return Torrent.format(source=source, **data)

    return _make
