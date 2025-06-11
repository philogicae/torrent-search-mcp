from fastapi import FastAPI, HTTPException, Path, Query
from pydantic import BaseModel

from .wrapper import Torrent, TorrentSearchApi

app = FastAPI(
    title="TorrentSearch FastAPI",
    description="FastAPI server for TorrentSearch API.",
)

api_client = TorrentSearchApi()


class MagnetLinkResponse(BaseModel):
    magnet_link: str


class SearchTorrentsRequest(BaseModel):
    query: str
    sources: list[str] | None = None
    max_items: int = 10


# --- API Endpoints ---
@app.get("/", summary="Health Check", tags=["General"])
async def health_check():
    """
    Endpoint to check the health of the service.
    """
    return {"status": "ok"}


@app.post(
    "/torrents/search",
    summary="Search Torrents",
    tags=["Torrents"],
    response_model=list[Torrent],
)
async def search_torrents(request_data: SearchTorrentsRequest):
    """
    Search for torrents on sources [thepiratebay.org, nyaa.si, yggtorrent].
    Corresponds to `TorrentSearchApi.search_torrents()`.
    """
    return await api_client.search_torrents(
        request_data.query,
        sources=request_data.sources,
        max_items=request_data.max_items,
    )


@app.get(
    "/torrents/{torrent_id}",
    summary="Get YGG Torrent Details",
    tags=["Torrents"],
    response_model=Torrent,
)
async def get_ygg_torrent_details(
    torrent_id: int = Path(..., ge=1, description="The ID of the torrent."),
    with_magnet_link: bool = Query(
        False, description="Include magnet link in the response."
    ),
):
    """
    Get details about a specific torrent coming from YGG Torrent source only.
    Corresponds to `TorrentSearchApi.get_ygg_torrent_details()`.
    """
    torrent = api_client.get_ygg_torrent_details(
        torrent_id, with_magnet_link=with_magnet_link
    )
    if not torrent:
        raise HTTPException(
            status_code=404, detail=f"Torrent with ID {torrent_id} not found."
        )
    return torrent


@app.get(
    "/torrents/{torrent_id}/magnet",
    summary="Get YGG Magnet Link",
    tags=["Torrents"],
    response_model=MagnetLinkResponse,
)
async def get_magnet_link(
    torrent_id: int = Path(..., ge=1, description="The ID of the torrent."),
):
    """
    Get the magnet link for a specific torrent coming from YGG Torrent source only.
    Corresponds to `TorrentSearchApi.get_ygg_magnet_link()`.
    """
    magnet = api_client.get_ygg_magnet_link(torrent_id)
    if not magnet:
        raise HTTPException(
            status_code=404, detail="Magnet link not found or could not be generated."
        )
    return MagnetLinkResponse(magnet_link=magnet)
