"""Package-level lazy exports: importing submodules must stay lightweight."""

import pytest

import torrent_search


def test_lazy_package_exports() -> None:
    assert torrent_search.Torrent.__name__ == "Torrent"
    assert torrent_search.torrent_search_api.__class__.__name__ == "TorrentSearchApi"
    assert torrent_search.torrent_search_app.title == "Torrent Search API"
    assert torrent_search.torrent_search_mcp.name == "Torrent Search Tools"


def test_lazy_package_unknown_attribute() -> None:
    with pytest.raises(AttributeError, match="has no attribute 'nope'"):
        _ = torrent_search.nope


def test_package_dir_lists_public_exports() -> None:
    assert dir(torrent_search) == sorted(torrent_search.__all__)
