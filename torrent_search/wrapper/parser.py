"""Torrent parsing: source parsers and the CSV text pipeline.

Each parser fetches its source over HTTP and normalizes the results into the
same ';'-separated CSV text, so ``extract_torrents`` handles every source
identically. Parsers are referenced from the ``WEBSITES`` registry in
:mod:`scraper`.
"""

import asyncio
import html
import json
import re
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from re import DOTALL, sub
from time import time
from typing import Any
from urllib.parse import quote

import httpx

from .models import Torrent

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SourceParser = Callable[[str], Awaitable[str]]

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
TIMEOUT = httpx.Timeout(20)

# Public trackers appended to magnets built from a bare info hash.
TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.demonii.com:1337/announce",
    "udp://tracker.openbittorrent.com:6969/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://exodus.desync.com:6969/announce",
    "udp://open.stealth.si:80/announce",
    "udp://tracker.dler.org:6969/announce",
    "http://tracker.opentrackr.org:1337/announce",
    "http://tracker.openbittorrent.com:80/announce",
    "http://tracker.dler.org:6969/announce",
    "https://tracker.tamersunion.org:443/announce",
]

TRACKERS_BEST_URL = (
    "https://raw.githubusercontent.com/ngosang/trackerslist/master/trackers_best.txt"
)

CSV_HEADER = "filename;category;size;seeders;leechers;downloads;date;magnet_link"

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

_trackers: list[str] = list(TRACKERS)
_trackers_loaded = False


def _merge_trackers(remote_text: str) -> list[str]:
    """Merge the remote tracker list into the base one, deduplicated."""
    remote = [
        line.strip()
        for line in remote_text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    return list(dict.fromkeys(TRACKERS + remote))


async def ensure_trackers() -> None:
    """Enrich TRACKERS with the ngosang trackers list, once per process.

    Falls back to the static TRACKERS on failure. Refresh via restart.
    """
    global _trackers, _trackers_loaded
    if _trackers_loaded:
        return
    _trackers_loaded = True
    with suppress(Exception):
        _trackers = _merge_trackers(await _get_text(TRACKERS_BEST_URL))


def build_magnet(info_hash: str, name: str) -> str:
    """Build a magnet URI from an info hash and display name."""
    trackers = "".join(f"&tr={quote(tracker, safe='')}" for tracker in _trackers)
    return f"magnet:?xt=urn:btih:{info_hash}&dn={quote(name, safe='')}{trackers}"


def human_size(num_bytes: Any) -> str:
    """Format a byte count as a human-readable string."""
    try:
        value = float(num_bytes or 0)
    except (TypeError, ValueError):
        return "N/A"
    if value <= 0:
        return "N/A"
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return "N/A"  # pragma: no cover - the TiB branch always returns


def fmt_date(value: Any) -> str:
    """Format a unix timestamp, ISO-8601 or RFC-822 date as YYYY-MM-DD."""
    if isinstance(value, bool):
        return "N/A"
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        ts = int(value)
        return (
            datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            if ts
            else "N/A"
        )
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime(
                "%Y-%m-%d"
            )
        except ValueError:
            try:
                return parsedate_to_datetime(value).strftime("%Y-%m-%d")
            except (TypeError, ValueError, IndexError):
                return "N/A"
    return "N/A"


def _row(
    filename: str,
    category: str,
    size: str,
    seeders: Any,
    leechers: Any,
    downloads: Any,
    date: Any,
    magnet_link: str,
) -> list[str]:
    return [
        filename.replace(";", ",").strip(),
        category,
        size,
        str(seeders or 0),
        str(leechers or 0),
        str(downloads) if downloads else "N/A",
        fmt_date(date),
        magnet_link,
    ]


def _format(rows: list[list[str]]) -> str:
    """Serialize rows to the CSV text extract_torrents expects."""
    if not rows:
        return "No results"
    return "\n".join([CSV_HEADER, *[";".join(row) for row in rows]])


_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Shared client reused across requests (connection pooling)."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=TIMEOUT, headers={"User-Agent": UA}, follow_redirects=True
        )
    return _client


async def _get_text(url: str, params: dict[str, str] | None = None) -> str:
    response = await _get_client().get(url, params=params)
    response.raise_for_status()
    return response.text


async def _get_json(url: str, params: dict[str, str] | None = None) -> Any:
    return json.loads(await _get_text(url, params))


_last_good_host: dict[tuple[str, ...], str] = {}


async def _first_host(
    hosts: list[str], path: str, params: dict[str, str] | None = None
) -> tuple[str, str]:
    """Fetch a path through a mirror rotation; returns the working (host, text).

    The last host that answered is tried first next time: mirrors that 403 or
    redirect cost several wasted round trips per fetch otherwise.
    """
    last_error: httpx.HTTPError | None = None
    preferred = _last_good_host.get(tuple(hosts))
    ordered = (
        [h for h in (preferred, *hosts) if h in hosts] if preferred else list(hosts)
    )
    for host in ordered:
        try:
            text = await _get_text(f"https://{host}{path}", params)
            _last_good_host[tuple(hosts)] = host
            return host, text
        except httpx.HTTPError as e:
            last_error = e
    if last_error:
        raise last_error
    raise RuntimeError(
        f"no hosts to try for {path}"
    )  # pragma: no cover - hosts are never empty


async def _get_first(
    hosts: list[str], path: str, params: dict[str, str] | None = None
) -> str:
    """Fetch a path through a mirror rotation, returning the first answer."""
    return (await _first_host(hosts, path, params))[1]


def _rss_field(item: str, name: str) -> str:
    """Extract a tag's text from a raw RSS item (handles CDATA)."""
    match = re.search(
        rf"<{re.escape(name)}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{re.escape(name)}>",
        item,
        re.DOTALL | re.IGNORECASE,
    )
    return match.group(1).strip() if match else ""


def extract_torrents(texts: list[str]) -> list[Torrent]:
    """
    Extract torrents from the parsed texts.

    Args:
        texts: The texts to extract torrents from.

    Returns:
        A list of torrent results.
    """
    torrents: list[Torrent] = []
    for text in texts:
        source, content = text.split("\n", 1)
        if "No results" in content:
            continue
        source = source[10:]
        data = content.splitlines()
        headers = data[0].split(";")
        for line in data[1:]:
            with suppress(Exception):
                values = line.split(";")
                if len(values) > len(headers):
                    extra_count = len(values) - len(headers)
                    # If extra values are at the end (trailing empty), just trim them
                    if all(not v.strip() for v in values[len(headers) :]):
                        values = values[: len(headers)]
                    elif len(values) > 1:
                        # Extra values mid-row (e.g. a ';' inside a filename):
                        # the extra fields right after the filename are joined
                        # back into it; the tail beyond the header length is
                        # dropped by zip
                        filename_parts = values[1 : 1 + extra_count]
                        values[1] = " - ".join(filename_parts)
                        del values[2 : 1 + extra_count]
                torrents.append(
                    Torrent.format(**dict(zip(headers, values)), source=source)
                )
    return torrents


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 1337x.to - HTML scrape with mirror rotation
# ---------------------------------------------------------------------------
X1337_HOSTS = ["1337x.to", "1337x.st", "x1337x.ws", "1337xx.to"]
X1337_STOP_WORDS = {"the", "a", "an", "of", "and", "or", "to"}
X1337_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def x1337_rows(html_text: str) -> list[list[str]]:
    """Parse the search-result table from a 1337x category page.

    Returns rows of [name, torrent_path, size, seeders, leechers].
    """
    start = html_text.find("table-list")
    if start < 0:
        return []
    rows: list[list[str]] = []
    for tr in html_text[start:].split("<tr")[1:]:
        link_match = re.search(
            r'href="(/torrent/[^"]+)"[^>]*>([^<]+)</a>', tr, re.IGNORECASE
        )
        if not link_match:
            continue
        size_match = re.search(
            r'class="coll-4 size[^"]*">\s*([\d.]+\s*[KMGT]i?B)', tr, re.IGNORECASE
        )
        seeds_match = re.search(
            r'class="coll-2 seeds[^"]*">\s*([\d,]+)', tr, re.IGNORECASE
        )
        leech_match = re.search(
            r'class="coll-3 leeches[^"]*">\s*([\d,]+)', tr, re.IGNORECASE
        )
        rows.append(
            [
                html.unescape(link_match.group(2).strip()),
                link_match.group(1),
                size_match.group(1) if size_match else "N/A",
                seeds_match.group(1).replace(",", "") if seeds_match else "0",
                leech_match.group(1).replace(",", "") if leech_match else "0",
            ]
        )
    return rows


def x1337_upload_date(html_text: str) -> str:
    """Parse the 'Date uploaded' field of a 1337x detail page."""
    match = re.search(
        r"Date uploaded</strong>\s*<span>\s*([A-Za-z]{3})\.?\s+(\d{1,2})[a-z]{2}\s*'(\d{2})",
        html_text,
        re.IGNORECASE,
    )
    if not match:
        return "N/A"
    month = X1337_MONTHS.get(match.group(1).lower())
    if not month:
        return "N/A"
    return f"{2000 + int(match.group(3))}-{month:02d}-{int(match.group(2)):02d}"


X1337_DETAIL_CONCURRENCY = 8
_x1337_detail_slots = asyncio.Semaphore(X1337_DETAIL_CONCURRENCY)


async def _x1337_fetch(path: str) -> tuple[str, str]:
    """Fetch a 1337x path through the mirror rotation; returns (base, html)."""
    host, detail_html = await _first_host(X1337_HOSTS, path)
    return f"https://{host}", detail_html


async def _x1337_detail(base: str, path: str) -> tuple[str, str] | None:
    """Fetch a torrent page and return (magnet, date); None on failure.

    Detail pages resolve through the mirror rotation (up to ~5 requests
    each), so concurrency is bounded to keep the mirror hosts from
    throttling the whole listing.
    """
    async with _x1337_detail_slots:
        try:
            detail_html = await _get_text(f"{base}{path}")
        except httpx.HTTPError:
            return None
    magnet_match = re.search(
        r"magnet:\?xt=urn:btih:[^\"'<>\s]+", detail_html, re.IGNORECASE
    )
    if not magnet_match:
        return None
    return html.unescape(magnet_match.group(0)), x1337_upload_date(detail_html)


async def x1337_parse(query: str) -> str:
    q = query.strip()
    if q:
        encoded = quote(q, safe="").replace("%20", "+")
        paths = [
            (f"/category-search/{encoded}/Movies/1/", "Video - Movies"),
            (f"/category-search/{encoded}/TV/1/", "Video - TV shows"),
        ]
    else:
        paths = [
            ("/popular-movies", "Video - Movies"),
            ("/popular-tv", "Video - TV shows"),
        ]

    tokens = [t for t in q.lower().split() if t not in X1337_STOP_WORDS] if q else []
    results: list[list[str]] = []
    pages = await asyncio.gather(
        *(_x1337_fetch(path) for path, _ in paths), return_exceptions=True
    )
    for (path, category), page in zip(paths, pages):
        if isinstance(page, BaseException):
            continue
        base, list_html = page
        rows = x1337_rows(list_html)
        if tokens:
            rows = [r for r in rows if all(t in r[0].lower() for t in tokens)]
        rows.sort(key=lambda r: int(r[3]), reverse=True)
        top = rows
        details = await asyncio.gather(
            *(_x1337_detail(base, row[1]) for row in top), return_exceptions=True
        )
        for row, detail in zip(top, details):
            if isinstance(detail, BaseException) or detail is None:
                continue
            name, _path, size, seeds, leeches = row
            magnet, date = detail
            results.append(
                _row(name, category, size, seeds, leeches, None, date, magnet)
            )
    return _format(results)


# ---------------------------------------------------------------------------
# apibay.org - The Pirate Bay JSON API
# ---------------------------------------------------------------------------
APIBAY_CATEGORIES = {
    200: "Video",
    201: "Video - Movies",
    202: "Video - Movies DVDR",
    205: "Video - TV shows",
    206: "Video - Handheld",
    207: "Video - Movies HD",
    208: "Video - Movies HD x265",
    209: "Video - Movies 3D",
}


def apibay_rows(items: list[dict[str, Any]]) -> list[list[str]]:
    rows: list[list[str]] = []
    for item in items:
        info_hash = (item.get("info_hash") or "").lower()
        if len(info_hash) != 40 or info_hash == "0" * 40 or item.get("id") == "0":
            continue
        name = item.get("name") or "Unknown"
        category_id = item.get("category")
        category = (
            APIBAY_CATEGORIES.get(int(category_id), "Video")
            if isinstance(category_id, str) and category_id.isdigit()
            else "Video"
        )
        rows.append(
            _row(
                name,
                category,
                human_size(item.get("size")),
                item.get("seeders"),
                item.get("leechers"),
                None,
                item.get("added"),
                build_magnet(info_hash, name),
            )
        )
    return rows


async def apibay_parse(query: str) -> str:
    q = query.strip()
    if q:
        data = await _get_json("https://apibay.org/q.php", {"q": q})
        items = data if isinstance(data, list) else []
    else:
        movies, tv = await asyncio.gather(
            _get_json("https://apibay.org/precompiled/data_top100_207.json"),
            _get_json("https://apibay.org/precompiled/data_top100_208.json"),
            return_exceptions=True,
        )
        items = [
            item for page in (movies, tv) if isinstance(page, list) for item in page
        ]
    return _format(apibay_rows(items))


# ---------------------------------------------------------------------------
# bittorrented.com - JSON API
# ---------------------------------------------------------------------------
def bittorrented_rows(data: dict[str, Any]) -> list[list[str]]:
    rows: list[list[str]] = []
    for item in data.get("results") or []:
        info_hash = (item.get("torrent_infohash") or "").lower()
        if not re.fullmatch(r"[a-f0-9]{40}", info_hash):
            continue
        name = item.get("torrent_name") or info_hash
        rows.append(
            _row(
                name,
                "Video",
                human_size(item.get("torrent_total_size")),
                item.get("torrent_seeders"),
                item.get("torrent_leechers"),
                None,
                item.get("torrent_created_at"),
                build_magnet(info_hash, name),
            )
        )
    return rows


async def bittorrented_parse(query: str) -> str:
    q = query.strip()
    # ponytail: the API rejects queries shorter than 3 characters
    if len(q) < 3:
        return "No results"
    data = await _get_json(
        "https://bittorrented.com/api/search/torrents",
        {
            "q": q,
            "type": "video",
            "limit": "50",
            "sortBy": "seeders",
            "sortOrder": "desc",
        },
    )
    return _format(bittorrented_rows(data if isinstance(data, dict) else {}))


# ---------------------------------------------------------------------------
# eztvx.to - JSON API
# ---------------------------------------------------------------------------
def eztv_rows(data: dict[str, Any]) -> list[list[str]]:
    rows: list[list[str]] = []
    for torrent in data.get("torrents") or []:
        info_hash = (torrent.get("hash") or "").lower()
        if not info_hash:
            continue
        name = torrent.get("filename") or torrent.get("title") or info_hash
        magnet = torrent.get("magnet_url") or build_magnet(info_hash, name)
        rows.append(
            _row(
                name,
                "Video - TV shows",
                human_size(torrent.get("size_bytes")),
                torrent.get("seeds"),
                torrent.get("peers"),
                None,
                torrent.get("date_released_unix"),
                magnet,
            )
        )
    return rows


async def eztv_parse(query: str) -> str:
    # ponytail: the EZTV API has no query search (it ignores `q`), so queries
    # are matched client-side against the latest releases
    data = await _get_json(
        "https://eztvx.to/api/get-torrents", {"limit": "100", "page": "1"}
    )
    rows = eztv_rows(data if isinstance(data, dict) else {})
    if tokens := [t for t in query.strip().lower().split() if t]:
        rows = [r for r in rows if all(t in r[0].lower() for t in tokens)]
    return _format(rows)


# ---------------------------------------------------------------------------
# fitgirl-repacks.site - WordPress RSS feed
# ---------------------------------------------------------------------------
def fitgirl_rows(xml: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for item in xml.split("<item>")[1:]:
        magnet_match = re.search(
            r'href="(magnet:\?xt=urn:btih:[^"]+)"', item, re.IGNORECASE
        )
        if not magnet_match:
            continue
        magnet = html.unescape(magnet_match.group(1))
        name = html.unescape(_rss_field(item, "title")) or "Unknown"
        rows.append(
            _row(name, "Games", "N/A", 0, 0, None, _rss_field(item, "pubDate"), magnet)
        )
    return rows


async def fitgirl_parse(query: str) -> str:
    base = "https://fitgirl-repacks.site"
    if query.strip():
        url = f"{base}/?s={quote(query.strip(), safe='')}&feed=rss2"
    else:
        url = f"{base}/feed/"
    return _format(fitgirl_rows(await _get_text(url)))


# ---------------------------------------------------------------------------
# nyaa.si - RSS feed
# ---------------------------------------------------------------------------
def nyaa_rss_rows(xml: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for item in xml.split("<item>")[1:]:
        info_hash = _rss_field(item, "nyaa:infoHash").lower()
        name = html.unescape(_rss_field(item, "title"))
        if not info_hash or not name:
            continue
        rows.append(
            _row(
                name,
                _rss_field(item, "nyaa:category") or "Anime",
                _rss_field(item, "nyaa:size") or "N/A",
                _rss_field(item, "nyaa:seeders"),
                _rss_field(item, "nyaa:leechers"),
                _rss_field(item, "nyaa:downloads"),
                _rss_field(item, "pubDate"),
                build_magnet(info_hash, name),
            )
        )
    return rows


async def nyaa_parse(query: str) -> str:
    xml = await _get_text(
        "https://nyaa.si/", {"page": "rss", "q": query, "c": "0_0", "f": "0"}
    )
    return _format(nyaa_rss_rows(xml))


NYAA_POPULAR_URL = "https://nyaa.si/"
NYAA_POPULAR_PARAMS = {"q": "", "s": "seeders", "o": "desc"}


def nyaa_html_rows(html_text: str) -> list[list[str]]:
    """Parse the HTML browse table (the RSS feed ignores sort params)."""
    rows: list[list[str]] = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html_text, DOTALL):
        name_match = re.search(r'<a href="/view/\d+" title="([^"]+)"', tr)
        magnet_match = re.search(r'href="(magnet:\?xt=urn:btih:[^"]+)"', tr)
        if not name_match or not magnet_match:
            continue
        cells = re.findall(r'<td class="text-center"[^>]*>(.*?)</td>', tr, DOTALL)
        ts_match = re.search(r'data-timestamp="(\d+)"', tr)
        # Cells: [links, size, date, seeders, leechers, downloads]
        if len(cells) < 6:
            continue
        seeds = re.search(r"([\d,]+)", cells[3])
        leechers = re.search(r"([\d,]+)", cells[4])
        downloads = re.search(r"([\d,]+)", cells[5])
        rows.append(
            _row(
                html.unescape(name_match.group(1)),
                "Anime",
                (cells[1].strip() or "N/A"),
                (seeds.group(1).replace(",", "") if seeds else 0),
                (leechers.group(1).replace(",", "") if leechers else 0),
                (downloads.group(1).replace(",", "") if downloads else None),
                (int(ts_match.group(1)) if ts_match else None),
                html.unescape(magnet_match.group(1)),
            )
        )
    return rows


async def nyaa_popular() -> str:
    """Most seeded listings; the HTML page honors sorting, the RSS feed does not."""
    html_text = await _get_text(NYAA_POPULAR_URL, NYAA_POPULAR_PARAMS)
    return _format(nyaa_html_rows(html_text))


# ---------------------------------------------------------------------------
# subsplease.org - JSON API
# ---------------------------------------------------------------------------
RES_PREFERENCE = ["1080", "720", "480"]


def _pick_download(downloads: list[dict[str, Any]]) -> dict[str, Any] | None:
    for resolution in RES_PREFERENCE:
        for download in downloads:
            if download.get("res") == resolution and download.get("magnet"):
                return download
    return next((d for d in downloads if d.get("magnet")), None)


def subsplease_rows(data: dict[str, Any]) -> list[list[str]]:
    rows: list[list[str]] = []
    for entry in data.values():
        download = _pick_download(entry.get("downloads") or [])
        if not download:
            continue
        magnet = download["magnet"]
        show = entry.get("show") or "Unknown"
        episode = f" - {entry['episode']}" if entry.get("episode") else ""
        name = f"{show}{episode} [{download.get('res') or '?'}p]"
        size_match = re.search(r"[?&]xl=(\d+)", magnet)
        size = human_size(int(size_match.group(1))) if size_match else "N/A"
        rows.append(
            _row(
                name,
                "Anime",
                size,
                0,
                0,
                None,
                entry.get("release_date"),
                magnet,
            )
        )
    return rows


async def subsplease_parse(query: str) -> str:
    q = query.strip()
    params: dict[str, str] = {"tz": "UTC"}
    if q:
        params["f"] = "search"
        params["s"] = q
    else:
        params["f"] = "latest"
    data = await _get_json("https://subsplease.org/api/", params)
    return _format(subsplease_rows(data if isinstance(data, dict) else {}))


# ---------------------------------------------------------------------------
# uindex.org - browse top list (search endpoint is Cloudflare-challenged)
# ---------------------------------------------------------------------------
UINDEX_TOP_URL = "https://uindex.org/top.php"

_UINDEX_AGE = re.compile(
    r"(\d+(?:\.\d+)?)\s+(second|minute|hour|day|week|month|year)s?\s+ago"
)
_UINDEX_AGE_SECONDS = {
    "second": 1,
    "minute": 60,
    "hour": 3600,
    "day": 86400,
    "week": 604800,
    "month": 2592000,
    "year": 31536000,
}


def _uindex_date(value: str) -> str:
    """Convert uIndex's relative ages ("2.9 days ago") to YYYY-MM-DD."""
    match = _UINDEX_AGE.search(value)
    if not match:
        return fmt_date(value)
    seconds = float(match.group(1)) * _UINDEX_AGE_SECONDS[match.group(2)]
    return datetime.fromtimestamp(time() - seconds, tz=timezone.utc).strftime(
        "%Y-%m-%d"
    )


def uindex_rows(html_text: str) -> list[list[str]]:
    """Parse the top-list table; the name link href is the magnet itself."""
    rows: list[list[str]] = []
    for tr in re.findall(r"<tr><td class=\"top-col-rank\">.*?</tr>", html_text, DOTALL):
        magnet_match = re.search(r'href="(magnet:\?xt=urn:btih:[^"]+)"', tr)
        name_match = re.search(r'class="sr-torrent-link"[^>]*>(.*?)</a>', tr, DOTALL)
        if not magnet_match or not name_match:
            continue
        cat_match = re.search(r"sr-cat-badge[^>]*>(?:<svg.*?</svg>)?\s*([^<]+)</a>", tr)
        size_match = re.search(r'class="sr-col-size">([^<]+)<', tr)
        date_match = re.search(r'class="sr-col-uploaded"[^>]*>([^<]+)<', tr)
        seeds_match = re.search(r'class="sr-seed">([\d,]+)<', tr)
        leech_match = re.search(r'class="sr-leech">([\d,]+)<', tr)
        rows.append(
            _row(
                html.unescape(
                    sub(
                        r"<[^>]+>",
                        " ",
                        sub(r"<span[^>]*>.*?</span>", "", name_match.group(1)),
                    )
                ).strip(),
                (cat_match.group(1).strip() if cat_match else "N/A"),
                (size_match.group(1) if size_match else "N/A"),
                (seeds_match.group(1).replace(",", "") if seeds_match else "0"),
                (leech_match.group(1).replace(",", "") if leech_match else "0"),
                None,
                (_uindex_date(date_match.group(1)) if date_match else "N/A"),
                html.unescape(magnet_match.group(1)),
            )
        )
    return rows


async def uindex_parse(query: str) -> str:
    # ponytail: /search.php is Cloudflare-challenged for non-browsers, but
    # /top.php is open and carries magnets inline, so queries are matched
    # client-side against the current top list (same approach as EZTV).
    xml = await _get_text(UINDEX_TOP_URL)
    rows = uindex_rows(xml)
    if tokens := [t for t in query.strip().lower().split() if t]:
        rows = [r for r in rows if all(t in r[0].lower() for t in tokens)]
    return _format(rows)


# ---------------------------------------------------------------------------
# yts.mx - JSON API
# ---------------------------------------------------------------------------
YTS_HOSTS = ["yts.mx", "yts.am", "yts.rs"]


def yts_rows(data: dict[str, Any]) -> list[list[str]]:
    rows: list[list[str]] = []
    for movie in data.get("data", {}).get("movies") or []:
        title = movie.get("title_long") or movie.get("title") or "Unknown"
        for torrent in movie.get("torrents") or []:
            info_hash = torrent.get("hash")
            if not info_hash:
                continue
            tag = " ".join(
                x for x in (torrent.get("quality"), torrent.get("type")) if x
            )
            filename = f"{title} [{tag}]" if tag else title
            rows.append(
                _row(
                    filename,
                    "Video - Movies",
                    human_size(torrent.get("size_bytes")),
                    torrent.get("seeds"),
                    torrent.get("peers"),
                    None,
                    movie.get("date_uploaded_unix"),
                    build_magnet(info_hash.lower(), filename),
                )
            )
    return rows


async def yts_parse(query: str, *, sort_by: str = "") -> str:
    q = query.strip()
    params: dict[str, str] = {"limit": "50"}
    if q:
        params["query_term"] = q
    else:
        params["sort_by"] = sort_by or "date_added"
    data = json.loads(await _get_first(YTS_HOSTS, "/api/v2/list_movies.json", params))
    return _format(yts_rows(data if isinstance(data, dict) else {}))


# ---------------------------------------------------------------------------
# Popular listings
# ---------------------------------------------------------------------------
# Sources exposing a top/popular listing. Each entry takes no query and
# returns the same CSV text contract as the search parsers.
POPULAR_SOURCES: dict[str, Callable[[], Awaitable[str]]] = {
    "apibay.org": lambda: apibay_parse(""),  # official TPB top100 (movies + HD)
    "uindex.org": lambda: uindex_parse(""),  # site-wide top list, magnets inline
    "1337x.to": lambda: x1337_parse(""),  # popular movies + TV pages
    "yts.mx": lambda: yts_parse("", sort_by="seeds"),  # most seeded uploads
    "nyaa.si": lambda: nyaa_popular(),  # HTML page honors seed sorting, RSS does not
    "eztvx.to": lambda: eztv_parse(""),  # latest releases as candidate pool
}
