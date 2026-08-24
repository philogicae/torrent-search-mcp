import argparse
import subprocess
import sys
from contextlib import suppress
from os import geteuid

import uvicorn
from playwright._impl._driver import compute_driver_executable, get_driver_env

from .mcp_server import mcp


def install_playwright_drivers() -> None:
    with suppress(Exception):
        driver_executable, driver_cli = compute_driver_executable()
        playwright_command = [driver_executable, driver_cli, "install"]
        if sys.platform != "win32" and geteuid() == 0:
            playwright_command.extend(["--with-deps", "chromium"])
        completed_process = subprocess.run(
            playwright_command,
            env=get_driver_env(),
            check=True,
        )
        if completed_process.returncode == 0:
            print("Playwright drivers installed.", file=sys.stderr)
            return
    print("Failed to install Playwright drivers.", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Torrent Search Server.")
    parser.add_argument(
        "--mode",
        type=str,
        choices=["cli", "stdio", "http", "sse", "streamable-http", "fastapi"],
        default="stdio",
        help="Mode to run in. Default: stdio.",
    )
    parser.add_argument(
        "--host", type=str, default="0.0.0.0", help="Host to bind the server to."
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind the server to. Default: 8000.",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of worker processes to use for the FastAPI server.",
    )
    parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Search query (used with --mode cli).",
    )

    args = parser.parse_args()

    install_playwright_drivers()

    if args.mode == "cli":
        from asyncio import run

        from .wrapper import TorrentSearchApi

        run(TorrentSearchApi().cli(args.query))
    elif args.mode == "fastapi":
        print(f"Starting FastAPI server on {args.host}:{args.port}", file=sys.stderr)
        uvicorn.run(
            "torrent_search.fastapi_server:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            workers=args.workers,
        )
    else:
        print(f"Starting MCP server on {args.host}:{args.port}", file=sys.stderr)
        mcp.run(
            transport=args.mode,
            **({} if args.mode == "stdio" else {"host": args.host, "port": args.port}),
        )


if __name__ == "__main__":  # pragma: no cover - module entry guard
    main()
