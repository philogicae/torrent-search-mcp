"""Tests for __main__.py: entry points and CLI mode dispatch."""

from typing import Any

import pytest

from torrent_search import __main__ as main_mod


@pytest.fixture(autouse=True)
def _no_real_servers(monkeypatch: Any) -> None:
    monkeypatch.setattr(main_mod.uvicorn, "run", _noop)


def _noop(*_args: Any, **_kwargs: Any) -> None:
    return None


def test_cli_mode(monkeypatch: Any, capsys: Any) -> None:
    class FakeApi:
        async def cli(self, query: str | None) -> None:
            print(f"cli called with query={query}")

    monkeypatch.setattr("torrent_search.wrapper.TorrentSearchApi", FakeApi)
    monkeypatch.setattr("sys.argv", ["prog", "--mode", "cli", "sample show"])
    main_mod.main()
    assert "cli called with query=sample show" in capsys.readouterr().out


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

    def fake_run_mcp(transport: str, host: str, port: int) -> None:
        seen["transport"] = transport
        seen["host"] = host
        seen["port"] = port

    monkeypatch.setattr(main_mod, "_run_mcp", fake_run_mcp)
    monkeypatch.setattr("sys.argv", ["prog"])
    main_mod.main()
    assert seen == {"transport": "stdio", "host": "0.0.0.0", "port": 8000}


def test_sse_mode_passes_host_and_port(monkeypatch: Any) -> None:
    seen: dict[str, Any] = {}

    def fake_run_mcp(transport: str, host: str, port: int) -> None:
        seen["transport"] = transport
        seen["host"] = host
        seen["port"] = port

    monkeypatch.setattr(main_mod, "_run_mcp", fake_run_mcp)
    monkeypatch.setattr(
        "sys.argv", ["prog", "--mode", "sse", "--host", "1.2.3.4", "--port", "8080"]
    )
    main_mod.main()
    assert seen == {"transport": "sse", "host": "1.2.3.4", "port": 8080}


def test_run_mcp_imports_and_runs(monkeypatch: Any) -> None:
    """The lazy MCP import keeps FastMCP out of CLI/API startup."""
    from torrent_search import mcp_server

    seen: dict[str, Any] = {}

    def fake_run(**kwargs: Any) -> None:
        seen.update(kwargs)

    monkeypatch.setattr(mcp_server.mcp, "run", fake_run)
    main_mod._run_mcp("http", "0.0.0.0", 8000)
    assert seen == {"transport": "http", "host": "0.0.0.0", "port": 8000}

    seen.clear()
    main_mod._run_mcp("stdio", "0.0.0.0", 8000)
    assert seen == {"transport": "stdio"}


def test_invalid_mode_exits(monkeypatch: Any) -> None:
    monkeypatch.setattr("sys.argv", ["prog", "--mode", "bogus"])
    with pytest.raises(SystemExit):
        main_mod.main()
