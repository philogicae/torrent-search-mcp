from hashlib import sha256
from time import time
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, field_validator

from .utils import Compress62


class Torrent(BaseModel):
    id: str
    filename: str
    category: str | None = None
    size: str
    seeders: int
    leechers: int
    downloads: int | str | None = None
    date: str
    magnet_link: str | None = None
    page_url: str | None = None
    uploader: str | None = None
    source: str | None = None

    @field_validator("page_url", mode="before")
    @classmethod
    def validate_page_url(cls, value: Any) -> str | None:
        if not isinstance(value, str) or not value:
            return None
        parsed = urlsplit(value)
        return value if parsed.scheme in {"http", "https"} and parsed.netloc else None

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
        data["downloads"] = data["downloads"] if data.get("downloads") else "N/A"
        return cls(**data)

    def prepend_info(self, query: str, max_items: int) -> None:
        self.id = f"{Compress62.compress(query)}-{max_items}-{self.id}"

    @staticmethod
    def extract_info(torrent_id: str) -> tuple[str, int, str, str]:
        compressed_query, max_items, source, ref_id = torrent_id.split("-", 3)
        return Compress62.decompress(compressed_query), int(max_items), source, ref_id

    def __str__(self) -> str:
        return str(self.model_dump(exclude_unset=True, exclude_none=True))


class ScrappedTorrent(BaseModel):
    torrent: Torrent
    timestamp: int


class Cache:
    """Long-lived torrent cache used only by get_torrent magnet lookups.

    Search results are never served directly from this cache; they are only
    stored here so that a later get_torrent call can return a magnet link
    without re-running the same query. Entries expire by TTL and by max size.
    """

    def __init__(self, ttl: int = 60 * 60, max_size: int = 5000):
        self.cache: dict[str, ScrappedTorrent] = {}
        self.ttl: int = ttl
        self.max_size: int = max_size

    def clean(self) -> None:
        deadline: int = int(time()) - self.ttl
        self.cache = dict(
            filter(
                lambda torrent: torrent[1].timestamp > deadline,
                self.cache.items(),
            )
        )  # Filter out torrents older than ttl

    def _enforce_size(self) -> None:
        if self.max_size <= 0:
            return
        over = len(self.cache) - self.max_size
        if over > 0:
            oldest = sorted(self.cache.items(), key=lambda item: item[1].timestamp)[
                :over
            ]
            for key, _ in oldest:
                del self.cache[key]

    def update(self, torrents: list[Torrent]) -> None:
        timestamp: int = int(time())
        self.cache.update(
            {
                torrent.id: ScrappedTorrent(torrent=torrent, timestamp=timestamp)
                for torrent in torrents
            }
        )
        self._enforce_size()

    def get(self, torrent_id: str) -> Torrent | None:
        item = self.cache.get(torrent_id)
        if item:
            item.timestamp = int(time())  # Refresh timestamp
            return item.torrent
        return None
