"""Unit tests for parser.py: helpers, row mappers and the CSV pipeline."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from torrent_search.wrapper import parser

MAGNET_40 = f"magnet:?xt=urn:btih:{'a' * 40}&dn=x"


def _extract(source: str, out: str) -> list[Any]:
    return parser.extract_torrents([f"SOURCE -> {source}\n{out}"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_merge_trackers() -> None:
    merged = parser._merge_trackers(
        "# comment\nudp://tracker.remote.example:1337/announce\n\n"
        "udp://tracker.opentrackr.org:1337/announce\nudp://tracker.remote.example:1337/announce\n"
    )
    assert merged[0] == "udp://tracker.opentrackr.org:1337/announce"  # base first
    assert "udp://tracker.remote.example:1337/announce" in merged
    assert len(merged) == len(set(merged))  # deduplicated
    assert "#" not in "".join(merged)


@pytest.mark.asyncio
async def test_ensure_trackers_enriches(monkeypatch: Any) -> None:
    remote = "udp://tracker.remote.example:1337/announce\n"
    monkeypatch.setattr(parser, "_get_text", _fake(remote))
    await parser.ensure_trackers()
    assert "udp://tracker.remote.example:1337/announce" in parser._trackers
    assert parser._trackers_loaded


@pytest.mark.asyncio
async def test_ensure_trackers_falls_back_on_failure(monkeypatch: Any) -> None:
    async def boom(_url: str, _params: Any = None) -> str:
        raise RuntimeError("network down")

    monkeypatch.setattr(parser, "_get_text", boom)
    await parser.ensure_trackers()
    assert parser._trackers == parser.TRACKERS
    assert parser._trackers_loaded  # only tried once per process


@pytest.mark.asyncio
async def test_ensure_trackers_idempotent_after_load(monkeypatch: Any) -> None:
    calls: list[str] = []

    async def spy(_url: str, _params: Any = None) -> str:
        calls.append(_url)
        return "udp://tracker.remote.example:1337/announce\n"

    monkeypatch.setattr(parser, "_get_text", spy)
    parser._trackers_loaded = True
    await parser.ensure_trackers()
    await parser.ensure_trackers()
    assert calls == []  # already loaded, no fetch


def test_get_client_reuses_instance() -> None:
    parser._client = None
    first = parser._get_client()
    second = parser._get_client()
    assert first is second
    assert isinstance(first, httpx.AsyncClient)
    parser._client = None


@pytest.mark.asyncio
async def test_get_text_and_get_json(monkeypatch: Any) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        @property
        def text(self) -> str:
            return '{"ok": 1}'

    async def fake_get(url: str, params: dict[str, str] | None = None) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr(parser, "_get_client", lambda: SimpleNamespace(get=fake_get))
    assert await parser._get_text("http://x") == '{"ok": 1}'
    assert await parser._get_json("http://x") == {"ok": 1}


def test_build_magnet() -> None:
    magnet = parser.build_magnet("a" * 40, "My Torrent & File")
    assert magnet.startswith(f"magnet:?xt=urn:btih:{'a' * 40}&dn=")
    assert "My%20Torrent%20%26%20File" in magnet
    assert "tracker.opentrackr.org" in magnet


def test_human_size() -> None:
    assert parser.human_size(0) == "N/A"
    assert parser.human_size(512) == "512 B"
    assert parser.human_size(487900000) == "465.3 MiB"
    assert parser.human_size(150389060754) == "140.1 GiB"
    assert parser.human_size("150389060754") == "140.1 GiB"
    assert parser.human_size("bogus") == "N/A"


def test_fmt_date() -> None:
    assert parser.fmt_date(None) == "N/A"
    assert parser.fmt_date(0) == "N/A"
    assert parser.fmt_date(True) == "N/A"
    assert parser.fmt_date(1614202551) == "2021-02-24T21:35:51+00:00"
    assert (
        parser.fmt_date("2026-03-02T10:06:49.527547+00:00")
        == "2026-03-02T10:06:49.527547+00:00"
    )
    assert (
        parser.fmt_date("Sat, 08 Aug 2026 18:16:12 +0000")
        == "2026-08-08T18:16:12+00:00"
    )
    assert parser.fmt_date("2026-01-01") == "2026-01-01"
    assert parser.fmt_date("garbage") == "N/A"


def test_rss_field_handles_cdata_and_case() -> None:
    item = "<item><title><![CDATA[My &amp; Title]]></title><nyaa:infoHash>abc</nyaa:infoHash></item>"
    assert parser._rss_field(item, "title") == "My &amp; Title"
    assert parser._rss_field(item, "nyaa:infohash") == "abc"
    assert parser._rss_field(item, "missing") == ""


def test_row_sanitizes_semicolons() -> None:
    row = parser._row("Name;With;Semi", "Video", "1 GB", 1, 2, None, None, MAGNET_40)
    assert row[0] == "Name,With,Semi"
    assert row[5] == "N/A"
    assert row[6] == "N/A"
    assert row[3] == "1"
    assert row[4] == "2"
    assert row[8] == ""


# ---------------------------------------------------------------------------
# HTTP fetch helpers
# ---------------------------------------------------------------------------


def _fake(value: Any) -> Any:
    async def fake_fn(*_args: Any, **_kwargs: Any) -> Any:
        if isinstance(value, Exception):
            raise value
        return value

    return fake_fn


@pytest.mark.asyncio
async def test_get_first_rotation(monkeypatch: Any) -> None:
    calls: list[str] = []

    async def flaky(url: str, params: dict[str, str] | None = None) -> str:
        calls.append(url)
        if "bad1" in url:
            raise httpx.ConnectError("down")
        return "ok"

    monkeypatch.setattr(parser, "_get_text", flaky)
    assert await parser._get_first(["bad1.example", "good.example"], "/path") == "ok"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_get_first_all_hosts_fail(monkeypatch: Any) -> None:
    async def flaky(url: str, params: dict[str, str] | None = None) -> str:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(parser, "_get_text", flaky)
    with pytest.raises(httpx.HTTPError):
        await parser._get_first(["a.example", "b.example"], "/path")


@pytest.mark.asyncio
async def test_get_first_no_hosts_raises() -> None:
    with pytest.raises(RuntimeError, match="no hosts"):
        await parser._get_first([], "/path")


# ---------------------------------------------------------------------------
# CSV extraction (extract_torrents)
# ---------------------------------------------------------------------------


def test_extract_torrents_from_csv_text() -> None:
    text = (
        "SOURCE -> apibay.org\n"
        + parser.CSV_HEADER
        + "\n"
        + "Breaking Bad S01 1080p;Video - Movies;1.2 GB;10;5;100;2026-01-01;magnet:?xt=urn:btih:abcdef&dn=x;\n"
        + "Better Call Saul S01 720p;Video - TV shows;800 MB;3;1;50;2025-06-01;magnet:?xt=urn:btih:fedcba&dn=y;"
    )
    torrents = parser.extract_torrents([text])
    assert len(torrents) == 2
    assert torrents[0].filename == "Breaking Bad S01 1080p"
    assert torrents[0].source == "apibay.org"
    assert torrents[0].seeders == 10
    assert torrents[0].date == "2026-01-01"
    assert torrents[0].magnet_link == "magnet:?xt=urn:btih:abcdef&dn=x"


def test_extract_torrents_skips_no_results() -> None:
    torrents = parser.extract_torrents(
        [
            "SOURCE -> eztvx.to\nNo results",
            f"SOURCE -> yts.mx\n{parser.CSV_HEADER}\nx;y;z;1;1;1;d;m",
        ]
    )
    assert len(torrents) == 1


def test_extract_torrents_trims_trailing_empty_values() -> None:
    text = (
        "SOURCE -> nyaa.si\n"
        f"{parser.CSV_HEADER}\n"
        "Name;Anime;1 GB;2;1;50;2026-01-01;magnet:?xt=urn:btih:aaa&dn=x;;"
    )
    torrents = parser.extract_torrents([text])
    assert len(torrents) == 1
    assert torrents[0].filename == "Name"


def test_extract_torrents_skips_malformed_rows() -> None:
    text = (
        "SOURCE -> nyaa.si\n"
        f"{parser.CSV_HEADER}\n"
        "Good;Anime;1 GB;2;1;50;2026-01-01;magnet:?xt=urn:btih:aaa&dn=x\n"
        "Bad;Anime;1 GB;not-a-number;1;50;2026-01-01;magnet:?xt=urn:btih:bbb&dn=x"
    )
    torrents = parser.extract_torrents([text])
    assert len(torrents) == 1
    assert torrents[0].filename == "Good"


def test_extract_torrents_merges_filename_overflow() -> None:
    # Extra fields beyond the header length are absorbed back into the row
    # (the overflow branch merges the filename parts and zip drops the tail).
    text = (
        "SOURCE -> nyaa.si\n"
        f"{parser.CSV_HEADER}\n"
        "Name;Anime;1 GB;2;1;50;2026-01-01;magnet:?xt=urn:btih:aaa&dn=x;;extra"
    )
    torrents = parser.extract_torrents([text])
    assert len(torrents) == 1
    assert torrents[0].filename == "Name"
    assert torrents[0].magnet_link == "magnet:?xt=urn:btih:aaa&dn=x"


# ---------------------------------------------------------------------------
# YTS
# ---------------------------------------------------------------------------


def test_yts_rows() -> None:
    data = {
        "data": {
            "movies": [
                {
                    "title_long": "Breaking Bad (2008)",
                    "date_uploaded_unix": 1614202551,
                    "torrents": [
                        {
                            "hash": "b" * 40,
                            "quality": "1080p",
                            "type": "webrip",
                            "size_bytes": 1_500_000_000,
                            "seeds": 5,
                            "peers": 2,
                        },
                        {
                            "hash": "c" * 40,
                            "quality": "720p",
                            "type": "bluray",
                            "size_bytes": 800_000_000,
                            "seeds": 1,
                            "peers": 0,
                        },
                    ],
                },
                {
                    "title_long": "No Torrents",
                    "torrents": [
                        {"quality": "1080p", "type": "webrip", "size_bytes": 1},
                        {"hash": "", "quality": "720p", "type": "web", "size_bytes": 1},
                    ],
                },
            ]
        }
    }
    rows = parser.yts_rows(data)
    assert len(rows) == 2
    assert rows[0][0] == "Breaking Bad (2008) [1080p webrip]"
    assert rows[0][1] == "Video - Movies"
    assert rows[0][6] == "2021-02-24T21:35:51+00:00"
    assert rows[0][7].startswith(f"magnet:?xt=urn:btih:{'b' * 40}")
    assert rows[0][8] == ""


@pytest.mark.asyncio
async def test_yts_parse(monkeypatch: Any) -> None:
    payload = json.dumps(
        {
            "data": {
                "movies": [
                    {
                        "title": "Test",
                        "torrents": [
                            {
                                "hash": "d" * 40,
                                "quality": "720p",
                                "type": "web",
                                "size_bytes": 1000,
                                "seeds": 3,
                                "peers": 1,
                            }
                        ],
                    }
                ]
            }
        }
    )
    monkeypatch.setattr(parser, "_get_first", _fake(payload))
    out = await parser.yts_parse("test")
    assert out.splitlines()[0] == parser.CSV_HEADER
    assert _extract("yts.mx", out)[0].filename == "Test [720p web]"


@pytest.mark.asyncio
async def test_yts_parse_browse_sets_sort_by(monkeypatch: Any) -> None:
    seen: dict[str, Any] = {}

    async def spy(
        hosts: list[str], path: str, params: dict[str, str] | None = None
    ) -> str:
        seen["params"] = params
        return '{"data": {"movies": []}}'

    monkeypatch.setattr(parser, "_get_first", spy)
    assert await parser.yts_parse("") == "No results"
    assert seen["params"] == {"limit": "50", "sort_by": "date_added"}


# ---------------------------------------------------------------------------
# apibay
# ---------------------------------------------------------------------------


def test_apibay_rows() -> None:
    items: list[dict[str, Any]] = [
        {
            "id": "1",
            "info_hash": "d" * 40,
            "name": "Show S01 1080p",
            "category": "205",
            "size": "1500000000",
            "seeders": "100",
            "leechers": "10",
            "added": "1614202551",
        },
        {
            "id": "0",
            "info_hash": "e" * 40,
            "name": "dead",
            "category": "0",
            "size": "0",
            "seeders": "0",
            "leechers": "0",
            "added": "0",
        },
        {
            "id": "2",
            "info_hash": "0" * 40,
            "name": "zero hash",
            "category": "0",
            "size": "0",
            "seeders": "0",
            "leechers": "0",
            "added": "0",
        },
        {
            "id": "3",
            "info_hash": "f" * 40,
            "name": "weird cat",
            "category": "zzz",
            "size": "0",
            "seeders": "0",
            "leechers": "0",
            "added": "0",
        },
    ]
    rows = parser.apibay_rows(items)
    assert len(rows) == 2
    assert rows[0][1] == "Video - TV shows"
    assert rows[0][3] == "100"
    assert rows[0][8] == "https://thepiratebay.org/description.php?id=1"
    assert rows[1][1] == "Video"


def test_apibay_rows_omits_page_url_without_id() -> None:
    rows = parser.apibay_rows(
        [
            {
                "info_hash": "a" * 40,
                "name": "missing id",
                "category": "200",
                "size": "1000",
                "seeders": "1",
                "leechers": "0",
                "added": "0",
            }
        ]
    )
    assert len(rows) == 1
    assert rows[0][8] == ""


@pytest.mark.asyncio
async def test_apibay_parse_search(monkeypatch: Any) -> None:
    payload = json.dumps(
        [
            {
                "id": "1",
                "info_hash": "d" * 40,
                "name": "Show",
                "category": "201",
                "size": "1000",
                "seeders": "1",
                "leechers": "0",
                "added": "0",
            }
        ]
    )
    monkeypatch.setattr(parser, "_get_json", _fake(json.loads(payload)))
    out = await parser.apibay_parse("breaking bad")
    assert _extract("apibay.org", out)[0].category == "Video - Movies"


@pytest.mark.asyncio
async def test_apibay_parse_browse_merges_top100(monkeypatch: Any) -> None:
    movies = json.dumps(
        [
            {
                "id": "1",
                "info_hash": "d" * 40,
                "name": "Movie",
                "category": "207",
                "size": "1000",
                "seeders": "1",
                "leechers": "0",
                "added": "0",
            }
        ]
    )
    tv = json.dumps(
        [
            {
                "id": "2",
                "info_hash": "e" * 40,
                "name": "Show",
                "category": "205",
                "size": "1000",
                "seeders": "2",
                "leechers": "0",
                "added": "0",
            }
        ]
    )

    async def fake_json(url: str, params: dict[str, str] | None = None) -> Any:
        if "207" in url:
            return json.loads(movies)
        if "208" in url:
            return json.loads(tv)
        return json.loads(movies)

    monkeypatch.setattr(parser, "_get_json", fake_json)
    out = await parser.apibay_parse("")
    torrents = _extract("apibay.org", out)
    assert len(torrents) == 2


# ---------------------------------------------------------------------------
# EZTV
# ---------------------------------------------------------------------------


def test_eztv_rows() -> None:
    data = {
        "torrents": [
            {
                "hash": "f" * 40,
                "filename": "Show S01E01 1080p",
                "magnet_url": f"magnet:?xt=urn:btih:{'f' * 40}&dn=provided",
                "size_bytes": "1500000000",
                "seeds": 50,
                "peers": 5,
                "date_released_unix": 1614202551,
            },
            {"hash": "", "filename": "no hash"},
        ]
    }
    rows = parser.eztv_rows(data)
    assert len(rows) == 1
    assert rows[0][7] == f"magnet:?xt=urn:btih:{'f' * 40}&dn=provided"
    assert rows[0][1] == "Video - TV shows"


@pytest.mark.asyncio
async def test_eztv_parse_filters_client_side(monkeypatch: Any) -> None:
    payload = {
        "torrents": [
            {
                "hash": "f" * 40,
                "filename": "Show S01E01 1080p",
                "magnet_url": MAGNET_40,
            },
            {"hash": "e" * 40, "filename": "Other Show 720p", "magnet_url": MAGNET_40},
        ]
    }
    monkeypatch.setattr(parser, "_get_json", _fake(payload))

    out = await parser.eztv_parse("show")
    assert len(_extract("eztvx.to", out)) == 2  # both contain "show"

    out = await parser.eztv_parse("other 720")
    torrents = _extract("eztvx.to", out)
    assert len(torrents) == 1
    assert torrents[0].filename == "Other Show 720p"

    assert await parser.eztv_parse("breaking bad") == "No results"


# ---------------------------------------------------------------------------
# uIndex
# ---------------------------------------------------------------------------


UINDEX_ROW = (
    '<tr><td class="top-col-rank"><span class="top-rank">1</span></td>'
    '<td class="sr-col-cat"><a href="top.php?c=2&amp;t=7d" class="sr-cat-badge"> TV</a></td>'
    '<td class="sr-col-name">'
    '<a href="magnet:?xt=urn:btih:{hash}&amp;dn=Name" class="sr-magnet" title="Download Magnet"></a> '
    '<a href="/details.php?id=123" class="sr-torrent-link">{name} <span class="top-new-badge">NEW</span></a></td>'
    '<td class="sr-col-size">517.00 MB</td>'
    '<td class="sr-col-uploaded" title="2.9 days ago">2.9 days ago</td>'
    '<td class="sr-col-seeders"><span class="sr-seed">12,422</span></td>'
    '<td class="sr-col-leechers"><span class="sr-leech">21,234</span></td></tr>'
)


def test_uindex_rows() -> None:
    html_text = (
        UINDEX_ROW.format(hash="a" * 40, name="Show S01E01 1080p")
        + '<tr><td class="top-col-rank"><span class="top-rank">9</span></td>'
        + '<td class="sr-col-name"><a href="/details.php?id=2">No Magnet</a></td></tr>'
        + "<tr><td>not a listing row</td></tr>"
    )
    rows = parser.uindex_rows(html_text)
    assert len(rows) == 1
    assert rows[0][0] == "Show S01E01 1080p"
    assert rows[0][1] == "TV"
    assert rows[0][3] == "12422"
    assert rows[0][4] == "21234"
    assert rows[0][7].startswith(f"magnet:?xt=urn:btih:{'a' * 40}")


def test_uindex_date_converts_relative_ages(monkeypatch: Any) -> None:
    fixed = 1_800_000_000  # frozen clock removes midnight-boundary flakiness
    monkeypatch.setattr(parser, "time", lambda: fixed)
    expected = datetime.fromtimestamp(fixed - 7200, tz=timezone.utc)
    assert parser._uindex_date("2 hours ago") == expected.strftime("%Y-%m-%d")
    assert len(parser._uindex_date("3 weeks ago")) == 10
    assert parser._uindex_date("2026-01-01") == "2026-01-01"


@pytest.mark.asyncio
async def test_uindex_parse_filters_client_side(monkeypatch: Any) -> None:
    body = UINDEX_ROW.format(
        hash="a" * 40, name="Ubuntu 24.04 LTS Desktop"
    ) + UINDEX_ROW.format(hash="b" * 40, name="Other Distro")
    monkeypatch.setattr(parser, "_get_text", _fake(body))

    out = await parser.uindex_parse("")
    assert len(_extract("uindex.org", out)) == 2

    out = await parser.uindex_parse("ubuntu lts")
    torrents = _extract("uindex.org", out)
    assert len(torrents) == 1
    assert torrents[0].filename == "Ubuntu 24.04 LTS Desktop"

    assert await parser.uindex_parse("breaking bad") == "No results"


# ---------------------------------------------------------------------------
# FitGirl
# ---------------------------------------------------------------------------


def test_fitgirl_rows() -> None:
    xml = f"""<rss><channel><item>
        <title>Game Repack</title>
        <pubDate>Sat, 08 Aug 2026 18:16:12 +0000</pubDate>
        <description><a href="magnet:?xt=urn:btih:{"a" * 40}&amp;dn=game&amp;tr=udp%3A%2F%2Ftracker%2Fannounce">magnet</a></description>
    </item><item><title>No Magnet</title></item></channel></rss>"""
    rows = parser.fitgirl_rows(xml)
    assert len(rows) == 1
    assert rows[0][0] == "Game Repack"
    assert rows[0][1] == "Games"
    assert "&dn=game" in rows[0][7]
    assert "&amp;" not in rows[0][7]
    assert rows[0][6] == "2026-08-08T18:16:12+00:00"
    assert rows[0][8] == ""


@pytest.mark.asyncio
async def test_fitgirl_parse_search_and_browse_urls(monkeypatch: Any) -> None:
    seen: list[str] = []
    xml = "<rss></rss>"

    async def spy(url: str, params: dict[str, str] | None = None) -> str:
        seen.append(url)
        return xml

    monkeypatch.setattr(parser, "_get_text", spy)
    assert await parser.fitgirl_parse("assassin") == "No results"
    assert "s=assassin" in seen[0]
    assert await parser.fitgirl_parse("") == "No results"
    assert seen[1].endswith("/feed/")


# ---------------------------------------------------------------------------
# SubsPlease
# ---------------------------------------------------------------------------


def test_subsplease_rows() -> None:
    data = {
        "Show - 1173": {
            "show": "Show",
            "episode": "1173",
            "page": "show",
            "release_date": "Sun, 09 Aug 2026 16:03:43 +0000",
            "downloads": [
                {
                    "res": "480",
                    "magnet": f"magnet:?xt=urn:btih:{'b' * 40}&xl=376124912",
                },
                {
                    "res": "1080",
                    "magnet": f"magnet:?xt=urn:btih:{'a' * 40}&xl=1500000000",
                },
            ],
        },
        "Broken": {"show": "Broken", "downloads": [{"res": "480"}]},
    }
    rows = parser.subsplease_rows(data)
    assert len(rows) == 1
    assert rows[0][0] == "Show - 1173 [1080p]"
    assert rows[0][2] == "1.4 GiB"
    assert rows[0][6] == "2026-08-09T16:03:43+00:00"
    assert rows[0][8] == "https://subsplease.org/shows/show/"


def test_pick_download_falls_back() -> None:
    downloads = [
        {"res": "480", "magnet": None},
        {"res": "2160", "magnet": "magnet:?xt=urn:btih:aa&xl=1"},
    ]
    picked = parser._pick_download(downloads)
    assert picked is not None and picked["res"] == "2160"
    assert parser._pick_download([]) is None


@pytest.mark.asyncio
async def test_subsplease_parse_search_and_latest(monkeypatch: Any) -> None:
    payload = json.dumps(
        {
            "Show - 1": {
                "show": "Show",
                "episode": "1",
                "downloads": [
                    {"res": "720", "magnet": f"magnet:?xt=urn:btih:{'a' * 40}&xl=1000"}
                ],
            }
        }
    )
    monkeypatch.setattr(parser, "_get_json", _fake(json.loads(payload)))
    out = await parser.subsplease_parse("one piece")
    assert _extract("subsplease.org", out)[0].filename == "Show - 1 [720p]"
    out = await parser.subsplease_parse("")
    assert _extract("subsplease.org", out)[0].filename == "Show - 1 [720p]"


# ---------------------------------------------------------------------------
# BitTorrented
# ---------------------------------------------------------------------------


def test_bittorrented_rows() -> None:
    data = {
        "results": [
            {
                "torrent_infohash": "aa" * 20,
                "torrent_name": "Show S01 1080p",
                "torrent_total_size": 5_600_000_000,
                "torrent_seeders": 106,
                "torrent_leechers": 66,
                "torrent_created_at": "2026-03-02T10:06:49+00:00",
            },
            {
                "torrent_infohash": "short",
                "torrent_name": "bad hash",
                "torrent_seeders": 1,
                "torrent_leechers": 0,
            },
        ]
    }
    rows = parser.bittorrented_rows(data)
    assert len(rows) == 1
    assert rows[0][0] == "Show S01 1080p"
    assert rows[0][6] == "2026-03-02T10:06:49+00:00"
    assert rows[0][8] == ""


@pytest.mark.asyncio
async def test_bittorrented_parse_min_query_and_results(monkeypatch: Any) -> None:
    assert await parser.bittorrented_parse("ab") == "No results"

    payload = json.dumps(
        {
            "results": [
                {
                    "torrent_infohash": "aa" * 20,
                    "torrent_name": "Show",
                    "torrent_total_size": 1000,
                    "torrent_seeders": 1,
                    "torrent_leechers": 0,
                    "torrent_created_at": None,
                }
            ]
        }
    )
    monkeypatch.setattr(parser, "_get_json", _fake(json.loads(payload)))
    out = await parser.bittorrented_parse("breaking bad")
    assert _extract("bittorrented.com", out)[0].filename == "Show"


# ---------------------------------------------------------------------------
# Nyaa
# ---------------------------------------------------------------------------


def test_nyaa_rss_rows() -> None:
    xml = f"""<rss><channel><item>
        <title>One.Piece.E1173.1080p.WEBRip.x265</title>
        <link>https://nyaa.si/download/2144394.torrent</link>
        <guid isPermaLink="true">https://nyaa.si/view/2144394</guid>
        <pubDate>Mon, 10 Aug 2026 08:09:35 -0000</pubDate>
        <nyaa:infoHash>{"c" * 40}</nyaa:infoHash>
        <nyaa:category>Anime - English-translated</nyaa:category>
        <nyaa:size>487.9 MiB</nyaa:size>
        <nyaa:seeders>75</nyaa:seeders>
        <nyaa:leechers>3</nyaa:leechers>
        <nyaa:downloads>153</nyaa:downloads>
    </item></channel></rss>"""
    rows = parser.nyaa_rss_rows(xml)
    assert len(rows) == 1
    assert rows[0][0] == "One.Piece.E1173.1080p.WEBRip.x265"
    assert rows[0][1] == "Anime - English-translated"
    assert rows[0][2] == "487.9 MiB"
    assert rows[0][3] == "75"
    assert rows[0][5] == "153"
    assert rows[0][7].startswith(f"magnet:?xt=urn:btih:{'c' * 40}")
    assert rows[0][8] == "https://nyaa.si/view/2144394"


@pytest.mark.asyncio
async def test_nyaa_parse(monkeypatch: Any) -> None:
    xml = f"<rss><item><title>T</title><nyaa:infoHash>{'c' * 40}</nyaa:infoHash></item></rss>"
    monkeypatch.setattr(parser, "_get_text", _fake(xml))
    out = await parser.nyaa_parse("one piece")
    assert _extract("nyaa.si", out)[0].filename == "T"


def test_nyaa_rss_rows_skips_items_without_hash_or_name() -> None:
    xml = (
        "<rss><item><title>No Hash</title></item>"
        "<item><nyaa:infoHash>" + "c" * 40 + "</nyaa:infoHash></item>"
        "<item><title>OK</title><nyaa:infoHash>"
        + "d" * 40
        + "</nyaa:infoHash></item></rss>"
    )
    rows = parser.nyaa_rss_rows(xml)
    assert len(rows) == 1
    assert rows[0][0] == "OK"


@pytest.mark.asyncio
async def test_nyaa_popular_parses_html_table(monkeypatch: Any) -> None:
    tr = (
        '<tr><td><a href="/?c=1_2">cat</a></td>'
        '<td colspan="2"><a href="/view/123" title="Show S01E01">x</a></td>'
        '<td class="text-center"><a href="/download/123.torrent">dl</a>'
        '<a href="magnet:?xt=urn:btih:{hash}&amp;dn=x">m</a></td>'
        '<td class="text-center">1.5 GiB</td>'
        '<td class="text-center" data-timestamp="1787497286">2026-08-23 15:01</td>'
        '<td class="text-center">3,442</td>'
        '<td class="text-center">91</td>'
        '<td class="text-center">12954</td></tr>'
    )
    seen: dict[str, Any] = {}

    async def spy(url: str, params: dict[str, str] | None = None) -> str:
        seen.update({"url": url, "params": params})
        return f"<table>{tr}{tr}</table>"

    monkeypatch.setattr(parser, "_get_text", spy)

    out = await parser.nyaa_popular()
    torrents = _extract("nyaa.si", out)
    assert len(torrents) == 2
    assert torrents[0].filename == "Show S01E01"
    assert torrents[0].size == "1.5 GiB"
    assert torrents[0].seeders == 3442
    assert torrents[0].leechers == 91
    assert torrents[0].downloads == "12954"
    assert torrents[0].date == "2026-08-23T15:01:26+00:00"
    assert torrents[0].page_url == "https://nyaa.si/view/123"
    assert torrents[0].magnet_link
    assert seen["url"] == parser.NYAA_POPULAR_URL
    assert seen["params"] == parser.NYAA_POPULAR_PARAMS


def test_nyaa_html_rows_skips_malformed_cells() -> None:
    no_cells = '<tr><td><a href="/view/1" title="No Cells">x</a></td></tr>'
    short = (
        '<tr><td colspan="2"><a href="/view/9" title="Short">x</a>'
        f'<a href="magnet:?xt=urn:btih:{"d" * 40}&amp;dn=x">m</a></td>'
        '<td class="text-center">1 GB</td></tr>'
    )
    ok = (
        '<tr><td><a href="/view/2" title="Good">x</a></td>'
        '<td colspan="2"><a href="/view/2" title="Good">x</a>'
        f'<a href="magnet:?xt=urn:btih:{"d" * 40}&amp;dn=x">m</a></td>'
        + "".join(
            f'<td class="text-center">{c}</td>'
            for c in ("dl", "1 GB", "2026-01-01", "5", "1", "10")
        )
        + "</tr>"
    )
    rows = parser.nyaa_html_rows(f"<table>{no_cells}{short}{ok}</table>")
    assert [r[0] for r in rows] == ["Good"]


# ---------------------------------------------------------------------------
# 1337x
# ---------------------------------------------------------------------------

X1337_HTML = """<table class="table-list">
    <tr><td><a href="/torrent/111/1/">Show S01 1080p</a></td>
        <td class="coll-2 seeds">1,234</td>
        <td class="coll-3 leeches">45</td>
        <td class="coll-4 size">1.2 GiB</td></tr>
    <tr><td><a href="/torrent/222/1/">Show S01 720p</a></td>
        <td class="coll-2 seeds">10</td>
        <td class="coll-3 leeches">5</td>
        <td class="coll-4 size">800 MB</td></tr>
    <tr><td><a href="/details/333">Not a torrent link</a></td>
        <td class="coll-2 seeds">1</td><td class="coll-3 leeches">1</td></tr>
</table>"""


def test_x1337_rows() -> None:
    rows = parser.x1337_rows(X1337_HTML)
    assert len(rows) == 2
    assert rows[0] == ["Show S01 1080p", "/torrent/111/1/", "1.2 GiB", "1234", "45"]
    assert parser.x1337_rows("<p>no table here</p>") == []


def test_x1337_upload_date() -> None:
    assert (
        parser.x1337_upload_date(
            "<strong>Date uploaded</strong><span>Jun. 26th  '26</span>"
        )
        == "2026-06-26"
    )
    assert parser.x1337_upload_date("<p>nothing</p>") == "N/A"
    assert (
        parser.x1337_upload_date(
            "<strong>Date uploaded</strong><span>Xxx. 26th  '26</span>"
        )
        == "N/A"
    )


@pytest.mark.asyncio
async def test_x1337_fetch_and_detail(monkeypatch: Any) -> None:
    async def flaky(url: str, params: dict[str, str] | None = None) -> str:
        if "good" in url:
            return f'<a href="magnet:?xt=urn:btih:{MAGNET_40[21:]}" />'
        if "nomagnet" in url:
            return "<html><p>no magnet here</p></html>"
        raise httpx.ConnectError("down")

    monkeypatch.setattr(parser, "_get_text", flaky)

    base, html_text = await parser._x1337_fetch("/good")
    assert base == "https://1337x.to"
    assert "magnet:" in html_text

    with pytest.raises(httpx.HTTPError):
        await parser._x1337_fetch("/bad")

    assert await parser._x1337_detail(base, "/good") is not None
    assert await parser._x1337_detail(base, "/bad") is None
    assert await parser._x1337_detail(base, "/nomagnet") is None


@pytest.mark.asyncio
async def test_x1337_parse_browse(monkeypatch: Any) -> None:
    async def fake_fetch(path: str) -> tuple[str, str]:
        html = X1337_HTML if "popular-movies" in path else "<p>no results</p>"
        return "https://1337xx.to", html

    async def fake_detail(base: str, path: str) -> tuple[str, str] | None:
        return f"magnet:?xt=urn:btih:{'d' * 40}&dn=x", "2026-06-26"

    monkeypatch.setattr(parser, "_x1337_fetch", fake_fetch)
    monkeypatch.setattr(parser, "_x1337_detail", fake_detail)
    out = await parser.x1337_parse("")
    torrents = _extract("1337x.to", out)
    assert len(torrents) == 2
    assert torrents[0].category == "Video - Movies"


@pytest.mark.asyncio
async def test_x1337_parse_limits_detail_fetches(monkeypatch: Any) -> None:
    calls: list[str] = []

    async def fake_fetch(path: str) -> tuple[str, str]:
        return "https://1337xx.to", X1337_HTML

    async def fake_detail(base: str, path: str) -> tuple[str, str] | None:
        calls.append(path)
        return f"magnet:?xt=urn:btih:{'d' * 40}&dn=x", "2026-06-26"

    monkeypatch.setattr(parser, "_x1337_fetch", fake_fetch)
    monkeypatch.setattr(parser, "_x1337_detail", fake_detail)
    torrents = _extract("1337x.to", await parser.x1337_parse("", max_items=1))
    assert len(torrents) == 1
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_x1337_parse_query(monkeypatch: Any) -> None:
    async def fake_fetch(path: str) -> tuple[str, str]:
        html = X1337_HTML if "Movies" in path else "<p>no results</p>"
        return "https://1337xx.to", html

    async def fake_detail(base: str, path: str) -> tuple[str, str] | None:
        return f"magnet:?xt=urn:btih:{'d' * 40}&dn=x", "2026-06-26"

    monkeypatch.setattr(parser, "_x1337_fetch", fake_fetch)
    monkeypatch.setattr(parser, "_x1337_detail", fake_detail)
    out = await parser.x1337_parse("show s01")
    torrents = _extract("1337x.to", out)
    assert len(torrents) == 2
    assert torrents[0].seeders == 1234
    assert torrents[0].date == "2026-06-26"
    assert torrents[0].page_url == "https://1337xx.to/torrent/111/1/"


@pytest.mark.asyncio
async def test_x1337_parse_skips_failed_details(monkeypatch: Any) -> None:
    async def fake_fetch(path: str) -> tuple[str, str]:
        html = X1337_HTML if "Movies" in path else "<p>no results</p>"
        return "https://1337xx.to", html

    async def fake_detail(base: str, path: str) -> tuple[str, str] | None:
        return None if path == "/torrent/222/1/" else (MAGNET_40, "2026-06-26")

    monkeypatch.setattr(parser, "_x1337_fetch", fake_fetch)
    monkeypatch.setattr(parser, "_x1337_detail", fake_detail)
    out = await parser.x1337_parse("show")
    assert len(_extract("1337x.to", out)) == 1


@pytest.mark.asyncio
async def test_x1337_parse_all_fetches_fail(monkeypatch: Any) -> None:
    async def fake_fetch(path: str) -> tuple[str, str]:
        raise RuntimeError("blocked")

    monkeypatch.setattr(parser, "_x1337_fetch", fake_fetch)
    assert await parser.x1337_parse("show") == "No results"
