from torrent_search.wrapper.utils import Compress62, prune_magnet


def test_compress_decompress_roundtrip() -> None:
    for text in ["", "hello", "breaking bad 2026", "héllo wörld 😀"]:
        assert Compress62.decompress(Compress62.compress(text)) == text


def test_compressed_differs_from_plaintext() -> None:
    assert Compress62.compress("hello") != "hello"


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


def test_prune_magnet_without_dn_yields_hash_only() -> None:
    magnet = f"magnet:?tr=udp%3A%2F%2Ft&xt=urn:btih:{HASH}"
    assert prune_magnet(magnet) == f"magnet:?xt=urn:btih:{HASH}&dn="
