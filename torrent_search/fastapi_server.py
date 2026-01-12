from fastapi import FastAPI, HTTPException, Path
from fastapi.responses import FileResponse

from .wrapper import Torrent, TorrentSearchApi

app = FastAPI(
    title="Torrent Search FastAPI",
    description="FastAPI server for Torrent Search API.",
)

api_client = TorrentSearchApi()


@app.get("/", summary="Health Check", tags=["General"], response_model=dict[str, str])
async def health_check() -> dict[str, str]:
    """
    Endpoint to check the health of the service.
    """
    return {"status": "ok"}


@app.post(
    "/torrent/search",
    summary="Search Torrents",
    tags=["Torrents"],
    response_model=list[Torrent],
)
async def search_torrents(
    query: str,
    max_items: int = 10,
) -> list[Torrent]:
    """
    Search for torrents on sources [thepiratebay.org, nyaa.si, yggtorrent].
    Corresponds to `TorrentSearchApi.search_torrents()`.
    """
    torrents: list[Torrent] = await api_client.search_torrents(query, max_items)
    return torrents


@app.get(
    "/torrent/{torrent_id}",
    summary="Get Magnet Link or Torrent File",
    tags=["Torrents"],
    response_model=str,
)
async def get_torrent(
    torrent_id: str = Path(..., description="The ID of the torrent."),
) -> str | FileResponse:
    """
    Get the magnet link or torrent file for a specific torrent by id.
    Corresponds to `TorrentSearchApi.get_torrent()`.
    """
    result: str | None = await api_client.get_torrent(torrent_id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail="Magnet link or torrent file not found or could not be generated.",
        )
    elif result.endswith(".torrent"):
        return FileResponse(
            path=result,
            media_type="application/x-bittorrent",
            filename=result.split("/")[-1],
        )
    return result
