import pytest

from torrent_search.wrapper.utils import MAX_QUERY_BYTES, Compress62, prune_magnet


def test_compress_decompress_roundtrip() -> None:
    for text in ["", "hello", "sample show 2026", "héllo wörld 😀"]:
        assert Compress62.decompress(Compress62.compress(text)) == text


def test_compressed_differs_from_plaintext() -> None:
    assert Compress62.compress("hello") != "hello"


def test_decompress_rejects_oversized_payload() -> None:
    bomb = Compress62.compress("x" * (MAX_QUERY_BYTES + 1))
    with pytest.raises(ValueError, match="size limit"):
        Compress62.decompress(bomb)


HASH = "ab" * 20
FULL_MAGNET = f"magnet:?xt=urn:btih:{HASH}&dn=Some+Show+1080p&tr=udp%3A%2F%2Ft1&xl=999"


def test_prune_magnet_strips_all_trackers_keeps_hash_and_dn() -> None:
    assert (
        prune_magnet(FULL_MAGNET)
        == f"magnet:?xt=urn:btih:{HASH}&dn=Some%20Show%201080p"
    )


def test_prune_magnet_display_name_override_is_url_encoded() -> None:
    assert (
        prune_magnet(FULL_MAGNET, "My Show S01 E02")
        == f"magnet:?xt=urn:btih:{HASH}&dn=My%20Show%20S01%20E02"
    )


def test_prune_magnet_passthrough_when_not_a_btih_magnet() -> None:
    assert prune_magnet("magnet:?dn=x") == "magnet:?dn=x"  # no info hash
    assert prune_magnet("https://example.com/a") == "https://example.com/a"
    assert prune_magnet("") == ""


def test_prune_magnet_rejects_percent_encoded_parameter_injection() -> None:
    """A crafted xt cannot smuggle a tracker through percent-decoding."""
    magnet = (
        "magnet:?xt=urn:btih:"
        + HASH
        + "%26tr%3Dudp%3A%2F%2Fevil.example%3A80%2Fannounce"
    )
    assert prune_magnet(magnet) == magnet  # unchanged: xt is not a bare hash


def test_prune_magnet_reads_uppercase_dn() -> None:
    magnet = f"magnet:?DN=Some+Show&xt=urn:btih:{HASH}"
    assert prune_magnet(magnet) == f"magnet:?xt=urn:btih:{HASH}&dn=Some%20Show"


def test_prune_magnet_accepts_base32_info_hash() -> None:
    hash32 = "A" * 32
    assert (
        prune_magnet(f"magnet:?xt=urn:btih:{hash32}&dn=x&tr=udp%3A%2F%2Ft")
        == f"magnet:?xt=urn:btih:{hash32}&dn=x"
    )


def test_prune_magnet_without_dn_yields_hash_only() -> None:
    magnet = f"magnet:?tr=udp%3A%2F%2Ft&xt=urn:btih:{HASH}"
    assert prune_magnet(magnet) == f"magnet:?xt=urn:btih:{HASH}&dn="
