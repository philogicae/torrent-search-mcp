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


def test_prepend_and_extract_info() -> None:
    t = _format()
    t.prepend_info("breaking bad", 10)
    query, max_items, source, ref_id = Torrent.extract_info(t.id)
    assert (query, max_items, source, ref_id) == (
        "breaking bad",
        10,
        "nyaa.si",
        sha256(MAGNET.encode()).hexdigest()[:10],
    )


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
