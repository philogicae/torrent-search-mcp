import re
from base64 import urlsafe_b64encode
from hashlib import sha256
from time import time
from typing import Any, TypeGuard
from urllib.parse import parse_qs, urlsplit

from pydantic import BaseModel, field_validator

from .utils import Compress62

_URLSAFE_ID_PART = re.compile(r"[A-Za-z0-9._~-]+\Z")
_BTIH_HEX = re.compile(r"urn:btih:[0-9a-fA-F]{40}\Z", re.IGNORECASE)
_BTIH_BASE32 = re.compile(r"urn:btih:[A-Za-z2-7]{32}\Z", re.IGNORECASE)
_REF_ID = re.compile(r"(?:[0-9a-f]{10,40}|none|\d+)\Z")


def _magnet_info_hash(value: Any) -> str | None:
    """Extract the normalized btih info hash from a magnet URI."""
    if not isinstance(value, str) or not value.lower().startswith("magnet:?"):
        return None
    try:
        params = parse_qs(urlsplit(value).query)
    except ValueError:  # pragma: no cover - magnet URIs have no netloc to fail
        return None
    for key, values in params.items():
        if key.lower() != "xt":
            continue
        for candidate in values:
            if _BTIH_HEX.fullmatch(candidate) or _BTIH_BASE32.fullmatch(candidate):
                return candidate.rsplit(":", 1)[-1].lower()
    return None


def is_magnet_link(value: Any) -> TypeGuard[str]:
    """True when ``value`` is a magnet URI carrying a valid v1 info hash."""
    return _magnet_info_hash(value) is not None


def _id_part(value: Any) -> str:
    """Encode one torrent id component as a single URL path segment.

    Hex hashes and scraping keys pass through unchanged; values with spaces,
    slashes or non-ASCII characters are base64url-encoded, so an id can never
    break out of ``/torrent/{id}`` routing with a raw ``/``.
    """
    text = str(value)
    if _URLSAFE_ID_PART.fullmatch(text):
        return text
    return urlsafe_b64encode(text.encode()).decode().rstrip("=")


def _as_int(value: Any) -> int:
    """Best-effort integer for scraped counters ("1,234" included)."""
    if isinstance(value, bool):
        return int(value)
    try:
        if isinstance(value, (int, float)):
            return int(value)
        return int(str(value or "").replace(",", "").strip())
    except (OverflowError, ValueError):
        return 0


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

    @field_validator("magnet_link", mode="before")
    @classmethod
    def validate_magnet_link(cls, value: Any) -> str | None:
        return value if is_magnet_link(value) else None

    @field_validator("page_url", mode="before")
    @classmethod
    def validate_page_url(cls, value: Any) -> str | None:
        if not isinstance(value, str) or not value:
            return None
        parsed = urlsplit(value)
        return value if parsed.scheme in {"http", "https"} and parsed.netloc else None

    @property
    def info_hash(self) -> str | None:
        """Normalized btih hash, or None when the magnet is missing/invalid."""
        return _magnet_info_hash(self.magnet_link)

    @classmethod
    def format(cls, **data: Any) -> "Torrent":
        magnet = data.get("magnet_link")
        valid_magnet = magnet if is_magnet_link(magnet) else None
        data["magnet_link"] = valid_magnet
        ref = data.get("id") or (
            sha256(valid_magnet.encode()).hexdigest()[:10] if valid_magnet else "none"
        )
        data["id"] = f"{_id_part(data['source'])}-{_id_part(ref)}"
        data["filename"] = " ".join(str(data["filename"]).split())
        data["seeders"] = _as_int(data.get("seeders"))
        data["leechers"] = _as_int(data.get("leechers"))
        data["downloads"] = data["downloads"] if data.get("downloads") else "N/A"
        return cls(**data)

    def prepend_info(self, query: str, max_items: int) -> None:
        self.id = f"{Compress62.compress(query)}-{max_items}-{self.id}"

    @staticmethod
    def extract_info(torrent_id: str) -> tuple[str, int, str, str]:
        compressed_query, max_items, remainder = torrent_id.split("-", 2)
        source, separator, ref_id = remainder.rpartition("-")
        if not separator or not _REF_ID.fullmatch(ref_id):
            # Old/manual ids may carry dashes inside the ref; fall back to the
            # historical split, which keeps the query and max_items usable.
            source, _, ref_id = remainder.partition("-")
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
        self.cache = {
            key: item for key, item in self.cache.items() if item.timestamp > deadline
        }

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
        if item is None:
            return None
        now = int(time())
        if item.timestamp <= now - self.ttl:
            # Never refresh an expired entry: doing so would keep it alive
            # forever for the torrents users look up most often.
            del self.cache[torrent_id]
            return None
        item.timestamp = now  # Refresh timestamp for a live entry
        return item.torrent
