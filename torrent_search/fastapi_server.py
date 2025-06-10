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
    limit: int | None = None


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
    response_model=list[Torrent] | None,
)
async def search_torrents(request_data: SearchTorrentsRequest):
    """
    Search for torrents on TorrentSearch.
    Corresponds to `TorrentSearchApi.search_torrents()`.
    """
    results = (api_client.search_torrents(request_data.query) or [])[
        : request_data.limit or 50
    ]
    if results is None:
        raise HTTPException(
            status_code=500, detail="Failed to fetch torrents from upstream API."
        )
    return results


@app.get(
    "/torrents/{torrent_id}",
    summary="Get Torrent Details",
    tags=["Torrents"],
    response_model=Torrent,
)
async def get_torrent_details(
    torrent_id: int = Path(..., ge=1, description="The ID of the torrent."),
    with_magnet_link: bool = Query(
        False, description="Include magnet link in the response."
    ),
):
    """
    Get details for a specific torrent.
    Corresponds to `TorrentSearchApi.get_torrent_details()`.
    """
    torrent = api_client.get_torrent_details(
        torrent_id, with_magnet_link=with_magnet_link
    )
    if not torrent:
        raise HTTPException(
            status_code=404, detail=f"Torrent with ID {torrent_id} not found."
        )
    return torrent


@app.get(
    "/torrents/{torrent_id}/magnet",
    summary="Get Magnet Link",
    tags=["Torrents"],
    response_model=MagnetLinkResponse,
)
async def get_magnet_link(
    torrent_id: int = Path(..., ge=1, description="The ID of the torrent."),
):
    """
    Get the magnet link for a specific torrent.
    Corresponds to `TorrentSearchApi.get_magnet_link()`.
    """
    magnet = api_client.get_magnet_link(torrent_id)
    if not magnet:
        raise HTTPException(
            status_code=404, detail="Magnet link not found or could not be generated."
        )
    return MagnetLinkResponse(magnet_link=magnet)
