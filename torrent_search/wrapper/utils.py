from datetime import datetime
from math import floor, log
from math import pow as pw
from typing import Any

from .models import Torrent


def format_size(size_bytes: int | None) -> str:
    """Converts a size in bytes to a human-readable string."""
    if size_bytes is None:
        return "N/A"
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(floor(log(size_bytes, 1024)))
    p = pw(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"


def format_date(date_str: str | None) -> str:
    """Converts an ISO date string to a human-readable string 'YYYY-MM-DD HH:MM:SS' or 'N/A' if input is None."""
    if date_str is None:
        return "N/A"
    return datetime.fromisoformat(date_str).strftime("%Y-%m-%d %H:%M:%S")


def format_torrent(torrent: dict[str, Any], source: str) -> Torrent:
    """Converts a torrent data dictionary from the API into a Torrent model instance."""
    return Torrent(
        id=torrent.get("id") or None,
        filename=torrent.get("title"),
        category=torrent.get("category_id") or None,
        size=format_size(torrent.get("size")),
        seeders=torrent.get("seeders"),
        leechers=torrent.get("leechers"),
        downloads=torrent.get("downloads") or None,
        date=format_date(torrent.get("uploaded_at")),
        magnet_link=None,
        uploader=torrent.get("uploader") or None,
        source=source,
    )
