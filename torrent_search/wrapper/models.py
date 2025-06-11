from pydantic import BaseModel


class Torrent(BaseModel):
    id: int | None = None
    filename: str
    category: str | None = None
    size: str
    seeders: int
    leechers: int
    downloads: int | None = None
    date: str
    magnet_link: str | None = None
    uploader: str | None = None
    source: str | None = None
