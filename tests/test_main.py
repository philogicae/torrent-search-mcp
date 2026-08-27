"""Tests for __main__.py: entry points and CLI mode dispatch."""

from typing import Any

import pytest

from torrent_search import __main__ as main_mod


@pytest.fixture(autouse=True)
def _no_real_servers(monkeypatch: Any) -> None:
    monkeypatch.setattr(main_mod.mcp, "run", _noop)
    monkeypatch.setattr(main_mod.uvicorn, "run", _noop)


def _noop(*_args: Any, **_kwargs: Any) -> None:
    return None


def test_cli_mode(monkeypatch: Any, capsys: Any) -> None:
    class FakeApi:
        async def cli(self, query: str | None) -> None:
            print(f"cli called with query={query}")

    monkeypatch.setattr("torrent_search.wrapper.TorrentSearchApi", FakeApi)
    monkeypatch.setattr("sys.argv", ["prog", "--mode", "cli", "breaking bad"])
    main_mod.main()
    assert "cli called with query=breaking bad" in capsys.readouterr().out


def test_cli_mode_without_query(monkeypatch: Any, capsys: Any) -> None:
    class FakeApi:
        async def cli(self, query: str | None) -> None:
            print(f"cli called with query={query}")

    monkeypatch.setattr("torrent_search.wrapper.TorrentSearchApi", FakeApi)
    monkeypatch.setattr("sys.argv", ["prog", "--mode", "cli"])
    main_mod.main()
    assert "cli called with query=None" in capsys.readouterr().out


def test_api_mode(monkeypatch: Any) -> None:
    seen: dict[str, Any] = {}

    def fake_uvicorn(app: str, **kwargs: Any) -> None:
        seen.update(kwargs)
        seen["app"] = app

    monkeypatch.setattr(main_mod.uvicorn, "run", fake_uvicorn)
    monkeypatch.setattr(
        "sys.argv",
        [
            "prog",
            "--mode",
            "api",
            "--host",
            "0.0.0.0",
            "--port",
            "9000",
            "--workers",
            "2",
        ],
    )
    main_mod.main()
    assert seen["app"] == "torrent_search.api_server:app"
    assert seen["port"] == 9000
    assert seen["workers"] == 2


def test_stdio_mode(monkeypatch: Any) -> None:
    seen: dict[str, Any] = {}

    def fake_mcp_run(transport: str, **kwargs: Any) -> None:
        seen["transport"] = transport
        seen["kwargs"] = kwargs

    monkeypatch.setattr(main_mod.mcp, "run", fake_mcp_run)
    monkeypatch.setattr("sys.argv", ["prog"])
    main_mod.main()
    assert seen["transport"] == "stdio"
    assert seen["kwargs"] == {}


def test_sse_mode_passes_host_and_port(monkeypatch: Any) -> None:
    seen: dict[str, Any] = {}

    def fake_mcp_run(transport: str, **kwargs: Any) -> None:
        seen["transport"] = transport
        seen["kwargs"] = kwargs

    monkeypatch.setattr(main_mod.mcp, "run", fake_mcp_run)
    monkeypatch.setattr(
        "sys.argv", ["prog", "--mode", "sse", "--host", "1.2.3.4", "--port", "8080"]
    )
    main_mod.main()
    assert seen["transport"] == "sse"
    assert seen["kwargs"] == {"host": "1.2.3.4", "port": 8080}


def test_invalid_mode_exits(monkeypatch: Any) -> None:
    monkeypatch.setattr("sys.argv", ["prog", "--mode", "bogus"])
    with pytest.raises(SystemExit):
        main_mod.main()
