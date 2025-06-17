from hashlib import sha256
from typing import Any

from pydantic import BaseModel


class Torrent(BaseModel):
    id: str
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
        data["id"] = (
            data["source"]
            + "-"
            + (
                str(data["id"])
                if data.get("id")
                else (
                    sha256(data["magnet_link"].encode()).hexdigest()[:10]
                    if data.get("magnet_link")
                    else "none"
                )
            )
        )
        data["seeders"] = int(data["seeders"]) if data.get("seeders") else 0
        data["leechers"] = int(data["leechers"]) if data.get("leechers") else 0
        data["downloads"] = int(data["downloads"]) if data.get("downloads") else 0
        return cls(**data)
