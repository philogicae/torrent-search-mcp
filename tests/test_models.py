from hashlib import sha256
from time import time

import pytest

from torrent_search.wrapper.models import Cache, Torrent

MAGNET = f"magnet:?xt=urn:btih:{'a' * 40}&dn=x"


def _format(**overrides: object) -> Torrent:
    data = {
        "filename": "  Show S01E01 1080p  ",
        "size": "1.2 GiB",
        "seeders": "10",
        "leechers": "5",
        "date": "2026-01-01T12:00:00",
        "magnet_link": MAGNET,
        "source": "nyaa.si",
    }
    data.update(overrides)
    return Torrent.format(**data)


def test_format_defaults() -> None:
    t = _format()
    assert t.filename == "Show S01E01 1080p"
    assert t.seeders == 10
    assert t.leechers == 5
    assert t.downloads == "N/A"
    assert t.date == "2026-01-01T12:00:00"
    assert t.id == "nyaa.si-" + sha256(MAGNET.encode()).hexdigest()[:10]
    assert t.category is None
    assert t.uploader is None


def test_format_missing_magnet_uses_none_id() -> None:
    t = _format(magnet_link=None)
    assert t.id == "nyaa.si-none"


def test_format_rejects_unsafe_magnet_links() -> None:
    for bad in (
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "magnet:?dn=no-hash",
        "magnet:?xt=urn:btih:not-a-hash",
        "https://example.com/x.torrent",
    ):
        t = _format(magnet_link=bad)
        assert t.magnet_link is None
        assert t.id == "nyaa.si-none"


def test_format_accepts_valid_magnet_variants() -> None:
    assert _format(magnet_link=MAGNET).magnet_link == MAGNET
    magnet = f"magnet:?dn=x&xt=urn:btih:{'b' * 40}&tr=udp%3A%2F%2Ft"
    assert _format(magnet_link=magnet).magnet_link == magnet
    assert _format(magnet_link=magnet).info_hash == "b" * 40
    base32 = "magnet:?xt=urn:btih:" + "A" * 32 + "&dn=x"
    assert _format(magnet_link=base32).magnet_link == base32


def test_info_hash_property() -> None:
    assert _format().info_hash == "a" * 40
    assert _format(magnet_link=None).info_hash is None
    assert _format(magnet_link="javascript:alert(1)").info_hash is None
    assert _format(magnet_link="magnet:?dn=x").info_hash is None
    base32 = _format(magnet_link="magnet:?xt=urn:btih:" + "A" * 32)
    assert base32.info_hash == "a" * 32


def test_format_collapses_whitespace_in_filenames() -> None:
    assert _format(filename="  Show\n\tS01E01  ").filename == "Show S01E01"


def test_format_bool_counters() -> None:
    assert _format(seeders=True, leechers=False).seeders == 1
    assert _format(seeders=float("nan"), leechers=float("inf")).seeders == 0
    assert _format(seeders=float("nan"), leechers=float("inf")).leechers == 0


def test_format_normalizes_page_url() -> None:
    assert _format(page_url="").page_url is None
    assert _format(page_url="javascript:alert(1)").page_url is None
    assert _format(page_url="//example.com/torrent").page_url is None
    assert _format(page_url="https://example.com/torrent").page_url == (
        "https://example.com/torrent"
    )


def test_format_non_numeric_seeders_default_to_zero() -> None:
    t = _format(seeders="", leechers=None)
    assert t.seeders == 0
    assert t.leechers == 0


def test_unsafe_source_still_builds_url_safe_ids() -> None:
    t = _format(source="weird source/ünïcode")
    assert "/" not in t.id
    assert " " not in t.id
    t.prepend_info("héllo wörld", 10)
    query, max_items, _, _ = Torrent.extract_info(t.id)
    assert query == "héllo wörld"
    assert max_items == 10
    assert "/" not in t.id and " " not in t.id


def test_safe_id_components_stay_readable() -> None:
    assert _format().id.startswith("nyaa.si-")


def test_prepend_and_extract_info() -> None:
    t = _format()
    t.prepend_info("sample show", 10)
    query, max_items, source, ref_id = Torrent.extract_info(t.id)
    assert (query, max_items, source, ref_id) == (
        "sample show",
        10,
        "nyaa.si",
        sha256(MAGNET.encode()).hexdigest()[:10],
    )


def test_extract_info_keeps_hyphenated_source() -> None:
    t = _format(source="fitgirl-repacks.site")
    t.prepend_info("sample game", 0)
    query, max_items, source, _ = Torrent.extract_info(t.id)
    assert (query, max_items, source) == ("sample game", 0, "fitgirl-repacks.site")


def test_extract_info_roundtrip_with_compress62() -> None:
    t = _format()
    t.prepend_info("héllo", 25)
    assert Torrent.extract_info(t.id)[0] == "héllo"


def test_extract_info_invalid_id_raises() -> None:
    with pytest.raises(ValueError):
        Torrent.extract_info("bogus")


def test_cache_update_get_refresh_and_clean() -> None:
    cache = Cache(ttl=60)
    first = _format(magnet_link=f"magnet:?xt=urn:btih:{'b' * 40}&dn=x")
    second = _format(magnet_link=f"magnet:?xt=urn:btih:{'c' * 40}&dn=x")
    cache.update([first, second])

    assert cache.get(first.id) is first
    assert cache.get("missing") is None

    refreshed = int(time()) + 1
    cache.cache[first.id].timestamp = refreshed
    cache.clean()
    assert cache.get(first.id) is first

    expired = int(time()) - 100
    cache.cache[first.id].timestamp = expired
    cache.clean()
    assert cache.get(first.id) is None


def test_cache_get_rejects_and_drops_expired_entry() -> None:
    """A direct get must not resurrect an expired entry by refreshing it."""
    cache = Cache(ttl=60)
    first = _format()
    cache.update([first])
    cache.cache[first.id].timestamp = int(time()) - 100
    assert cache.get(first.id) is None
    assert first.id not in cache.cache


def test_cache_enforces_max_size() -> None:
    cache = Cache(ttl=60, max_size=2)
    first = _format(magnet_link=f"magnet:?xt=urn:btih:{'b' * 40}&dn=x")
    second = _format(magnet_link=f"magnet:?xt=urn:btih:{'c' * 40}&dn=x")
    third = _format(magnet_link=f"magnet:?xt=urn:btih:{'d' * 40}&dn=x")
    cache.update([first])
    cache.update([second])
    cache.update([third])
    assert first.id not in cache.cache
    assert second.id in cache.cache
    assert third.id in cache.cache


def test_cache_max_size_zero_is_unbounded() -> None:
    cache = Cache(ttl=60, max_size=0)
    for i in range(5):
        torrent = _format(magnet_link=f"magnet:?xt=urn:btih:{i:040x}&dn={i}")
        cache.update([torrent])
    assert len(cache.cache) == 5
