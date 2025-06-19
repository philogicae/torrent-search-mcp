from hashlib import sha256
from time import time
from typing import Any

from pydantic import BaseModel

from .utils import Compress62


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
            + str(
                data.get("id")
                or (
                    sha256(data["magnet_link"].encode()).hexdigest()[:10]
                    if data.get("magnet_link")
                    else "none"
                )
            )
        )
        data["filename"] = data["filename"].strip()
        data["seeders"] = int(data["seeders"]) if data.get("seeders") else 0
        data["leechers"] = int(data["leechers"]) if data.get("leechers") else 0
        data["downloads"] = int(data["downloads"]) if data.get("downloads") else None
        data["date"] = data["date"][:10]
        return cls(**data)

    def prepend_info(self, query: str, max_items: int) -> None:
        self.id = f"{Compress62.compress(query)}-{max_items}-{self.id}"

    @staticmethod
    def extract_info(torrent_id: str) -> tuple[str, int, str, str]:
        compressed_query, max_items, source, ref_id = torrent_id.split("-")
        return Compress62.decompress(compressed_query), int(max_items), source, ref_id

    def __str__(self) -> str:
        return str(self.model_dump(exclude_unset=True, exclude_none=True))


class ScrappedTorrent(BaseModel):
    torrent: Torrent
    timestamp: int


class Cache:
    def __init__(self, ttl: int = 60 * 60):
        self.cache: dict[str, ScrappedTorrent] = {}
        self.ttl: int = ttl

    def clean(self) -> None:
        deadline: int = int(time()) - self.ttl
        self.cache = dict(
            filter(
                lambda torrent: torrent[1].timestamp > deadline,
                self.cache.items(),
            )
        )  # Filter out torrents older than ttl

    def update(self, torrents: list[Torrent]) -> None:
        timestamp: int = int(time())
        self.cache.update(
            {
                torrent.id: ScrappedTorrent(torrent=torrent, timestamp=timestamp)
                for torrent in torrents
            }
        )

    def get(self, torrent_id: str) -> Torrent | None:
        item = self.cache.get(torrent_id)
        if item:
            item.timestamp = int(time())  # Refresh timestamp
            return item.torrent
        return None
