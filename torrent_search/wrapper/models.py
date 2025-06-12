from typing import Any

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

    @classmethod
    def format(cls, **data: Any) -> "Torrent":
        data["seeders"] = int(data["seeders"])
        data["leechers"] = int(data["leechers"])
        if "downloads" in data:
            data["downloads"] = int(data["downloads"])
        return cls(**data)
