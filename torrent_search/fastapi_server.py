from fastapi import FastAPI, HTTPException, Path
from fastapi.responses import FileResponse

from .wrapper import Torrent, TorrentSearchApi

app = FastAPI(
    title="TorrentSearch FastAPI",
    description="FastAPI server for TorrentSearch API.",
)

api_client = TorrentSearchApi()


@app.get("/", summary="Health Check", tags=["General"], response_model=dict[str, str])
async def health_check() -> dict[str, str]:
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
    "/torrents/{torrent_id}",
    summary="Get Torrent Details",
    tags=["Torrents"],
    response_model=Torrent,
)
async def get_torrent_details(
    torrent_id: str = Path(..., description="The ID of the torrent."),
) -> Torrent:
    """
    Get details about a specific torrent by id.
    Corresponds to `TorrentSearchApi.get_torrent_details()`.
    """
    torrent: Torrent | None = await api_client.get_torrent_details(torrent_id)
    if not torrent:
        raise HTTPException(
            status_code=404, detail=f"Torrent with ID {torrent_id} not found."
        )
    return torrent


@app.get(
    "/torrents/{torrent_id}/download",
    summary="Get Magnet Link or Torrent File",
    tags=["Torrents"],
    response_model=str,
)
async def get_magnet_link_or_torrent_file(
    torrent_id: str = Path(..., description="The ID of the torrent."),
) -> str | FileResponse:
    """
    Get the magnet link or torrent file for a specific torrent by id.
    Corresponds to `TorrentSearchApi.get_magnet_link_or_torrent_file()`.
    """
    magnet_link_or_torrent_file: (
        str | None
    ) = await api_client.get_magnet_link_or_torrent_file(torrent_id)
    if not magnet_link_or_torrent_file:
        raise HTTPException(
            status_code=404,
            detail="Magnet link or torrent file not found or could not be generated.",
        )
    elif magnet_link_or_torrent_file.endswith(".torrent"):
        return FileResponse(
            path=magnet_link_or_torrent_file,
            media_type="application/x-bittorrent",
            filename=magnet_link_or_torrent_file.split("/")[-1],
        )
    return magnet_link_or_torrent_file
