from typing import Any

from dotenv import load_dotenv

load_dotenv()

__all__ = [
    "Torrent",
    "torrent_search_api",
    "torrent_search_app",
    "torrent_search_mcp",
]


def __getattr__(name: str) -> Any:
    """Import the heavy app/tool objects only when they are actually used.

    Importing ``torrent_search.wrapper`` (CLI mode, tests) must not build the
    FastAPI app, minify the Web UI or create the Telegram auth store.
    """
    if name == "Torrent":
        from .wrapper import Torrent

        return Torrent
    if name == "torrent_search_api":
        from .mcp_server import torrent_search_api

        return torrent_search_api
    if name == "torrent_search_app":
        from .api_server import app

        return app
    if name == "torrent_search_mcp":
        from .mcp_server import mcp

        return mcp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
