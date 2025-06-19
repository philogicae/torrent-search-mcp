from fastapi import FastAPI, HTTPException, Path

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
    "/torrents/{torrent_id}/magnet",
    summary="Get Magnet Link",
    tags=["Torrents"],
    response_model=str,
)
async def get_magnet_link(
    torrent_id: str = Path(..., description="The ID of the torrent."),
) -> str:
    """
    Get the magnet link for a specific torrent by id.
    Corresponds to `TorrentSearchApi.get_magnet_link()`.
    """
    magnet_link: str | None = await api_client.get_magnet_link(torrent_id)
    if not magnet_link:
        raise HTTPException(
            status_code=404, detail="Magnet link not found or could not be generated."
        )
    return magnet_link
