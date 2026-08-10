from torrent_search.wrapper.utils import Compress62


def test_compress_decompress_roundtrip() -> None:
    for text in ["", "hello", "breaking bad 2026", "héllo wörld 😀"]:
        assert Compress62.decompress(Compress62.compress(text)) == text


def test_compressed_differs_from_plaintext() -> None:
    assert Compress62.compress("hello") != "hello"
