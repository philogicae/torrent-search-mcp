import json
from os import getenv
from pathlib import Path as PathLib

from fastapi import FastAPI, HTTPException, Path, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from minify_html import minify

from .wrapper import Torrent, TorrentSearchApi

app = FastAPI(
    title="Torrent Search FastAPI",
    description="FastAPI server for Torrent Search API.",
)
api_client = TorrentSearchApi()
app.add_middleware(GZipMiddleware, minimum_size=1024)
_STATIC_DIR = PathLib(__file__).parent / "static"
_TELEGRAM_BOT_HANDLE = getenv("TELEGRAM_BOT_HANDLE") or None
_TELEGRAM_BOT_HANDLE_JSON = json.dumps(_TELEGRAM_BOT_HANDLE).replace("<", "\\u003c")
_WEBUI_HTML = minify(
    (_STATIC_DIR / "index.html")
    .read_text(encoding="utf-8")
    .replace("__TELEGRAM_BOT_HANDLE__", _TELEGRAM_BOT_HANDLE_JSON),
    minify_css=True,
    minify_js=True,
)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get(
    "/",
    summary="Web UI",
    tags=["Webui"],
)
async def webui() -> Response:
    """
    Serve the bundled dark-mode web UI (minified).
    """
    return Response(content=_WEBUI_HTML, media_type="text/html")


@app.get("/sources", summary="List Sources", tags=["General"], response_model=list[str])
async def list_sources() -> list[str]:
    """
    Endpoint listing the available torrent sources.
    """
    return api_client.available_sources()


@app.get(
    "/torrent/popular",
    summary="Popular Torrents",
    tags=["Torrents"],
    response_model=list[Torrent],
)
async def popular_torrents(response: Response, per_source: int = 10) -> list[Torrent]:
    """
    Get the most popular torrents across sources with a top listing,
    keeping up to `per_source` results from each. Cached server-side for
    2 minutes; the response is marked no-store so browsers always re-fetch.
    Corresponds to `TorrentSearchApi.popular_torrents()`.
    """
    response.headers.update(
        {
            "Cache-Control": "no-cache, no-store",
            "Pragma": "no-cache",
            "Expires": "0",
        }
    )
    torrents: list[Torrent] = await api_client.popular_torrents(per_source)
    return torrents


@app.post(
    "/torrent/search",
    summary="Search Torrents",
    tags=["Torrents"],
    response_model=list[Torrent],
)
async def search_torrents(
    response: Response,
    query: str,
    max_items: int = 20,
) -> list[Torrent]:
    """
    Search for torrents across all enabled sources.
    Corresponds to `TorrentSearchApi.search_torrents()`.
    """
    response.headers.update(
        {
            "Cache-Control": "no-cache, no-store",
            "Pragma": "no-cache",
            "Expires": "0",
        }
    )
    torrents: list[Torrent] = await api_client.search_torrents(query, max_items)
    return torrents


@app.get(
    "/torrent/{torrent_id}",
    summary="Get Magnet Link",
    tags=["Torrents"],
    response_model=str,
)
async def get_torrent(
    torrent_id: str = Path(..., description="The ID of the torrent."),
) -> str:
    """
    Get the magnet link for a specific torrent by id.
    Corresponds to `TorrentSearchApi.get_torrent()`.
    """
    result: str | None = await api_client.get_torrent(torrent_id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail="Magnet link not found.",
        )
    return result
