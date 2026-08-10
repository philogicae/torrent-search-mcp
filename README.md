# Torrent Search MCP Server & API

[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://docs.astral.sh/uv/getting-started/installation/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![PyPI](https://badge.fury.io/py/torrent-search-mcp.svg?cache-control=no-cache)](https://badge.fury.io/py/torrent-search-mcp)
[![Actions status](https://github.com/philogicae/torrent-search-mcp/actions/workflows/python-package-ci.yml/badge.svg?cache-control=no-cache)](https://github.com/philogicae/torrent-search-mcp/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/philogicae/torrent-search-mcp)

This repository provides a Python API and an MCP (Model Context Protocol) server to find torrents programmatically on **ThePirateBay**, **Nyaa**, **1337x**, **YTS**, **FitGirl**, **EZTV**, **SubsPlease** and **BitTorrented**. It allows for easy integration into other applications or services.

<a href="https://glama.ai/mcp/servers/@philogicae/torrent-search-mcp">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/@philogicae/torrent-search-mcp/badge?cache-control=no-cache" alt="Torrent Search MCP server" />
</a>

## Quickstart

> [How to use it with MCP Clients](#via-mcp-clients)

> [Run it with Docker to bypass common DNS issues](#for-docker)

> [Search directly from the command line](#as-cli)

```bash
# One-time setup: install playwright/chromium for crawl4ai
uvx --from torrent-search-mcp crawl4ai-setup

# CLI search
uvx torrent-search-mcp --mode cli "breaking bad"

# MCP server over stdio (default)
uvx torrent-search-mcp --mode stdio

# MCP server over streamable HTTP (port 8000, endpoint /mcp)
uvx torrent-search-mcp --mode http

# MCP server over SSE (port 8000, endpoint /sse, legacy)
uvx torrent-search-mcp --mode sse

# Standalone FastAPI server (port 8000)
uvx torrent-search-mcp --mode fastapi
```

## Table of Contents

- [Features](#features)
- [Supported Sources](#supported-sources)
- [Setup](#setup)
  - [Prerequisites](#prerequisites)
  - [Configuration](#configuration-optional)
  - [Installation](#installation)
    - [Install from PyPI (Recommended)](#install-from-pypi-recommended)
    - [For Local Development](#for-local-development)
    - [For Docker](#for-docker)
- [Usage](#usage)
  - [As CLI](#as-cli)
  - [As Python Wrapper](#as-python-wrapper)
  - [As MCP Server](#as-mcp-server)
  - [As FastAPI Server](#as-fastapi-server)
  - [Via MCP Clients](#via-mcp-clients)
    - [Example with Devin](#example-with-devin)
- [Changelog](#changelog)
- [Contributing](#contributing)
- [License](#license)

## Features

- API wrapper for **ThePirateBay**, **Nyaa**, **1337x**, **YTS**, **FitGirl**, **EZTV**, **SubsPlease** and **BitTorrented**.
- MCP server interface for standardized communication (`stdio`, `sse`, `streamable-http`).
- FastAPI server interface for alternative HTTP access (e.g., for direct API calls or testing).
- CLI mode for quick one-off searches directly from the terminal.
- In-memory + `aiocache` result caching to reduce redundant scraping.
- Configurable source filtering and torrent file download folder via environment variables.
- Tools:
  - Search for torrents across all available sources.
  - Get magnet link or torrent file for a specific torrent by id.

## Supported Sources

| Source              | Domain                 | Fetch method    |
| ------------------- | ---------------------- | --------------- |
| ThePirateBay        | `thepiratebay.org`     | HTML (crawl4ai) |
| Nyaa                | `nyaa.si`              | HTTP API        |
| 1337x               | `1337x.to`             | HTTP API        |
| YTS                 | `yts.mx`               | HTTP API        |
| FitGirl             | `fitgirl-repacks.site` | HTTP API        |
| EZTV                | `eztvx.to`             | HTTP API        |
| SubsPlease          | `subsplease.org`       | HTTP API        |
| BitTorrented        | `bittorrented.com`     | HTTP API        |
| apibay (TPB mirror) | `apibay.org`           | HTTP API        |

Sources can be excluded individually via the [`EXCLUDE_SOURCES`](#configuration-optional) env var.

## Setup

### Prerequisites

- Python 3.10+ (required for PyPI install). CI and Docker images use Python 3.14.
- [`uv`](https://github.com/astral-sh/uv) (for local development).
- Docker and Docker Compose (for Docker setup).

### Configuration (Optional)

The application reads configuration from environment variables. The recommended way to set them is by creating a `.env` file in your project's root directory. The application will load it automatically. See `.env.example` for all available options.

| Variable               | Default      | Description                                                                                                                             |
| ---------------------- | ------------ | --------------------------------------------------------------------------------------------------------------------------------------- |
| `INCLUDE_LINKS`        | `false`      | When `true`, include magnet links / torrent file paths in `search_torrents` results. Left off by default to greatly reduce token usage. |
| `EXCLUDE_SOURCES`      | _(none)_     | Comma-separated list of sources to exclude from results (e.g. `nyaa.si,1337x.to`).                                                      |
| `FOLDER_TORRENT_FILES` | `./torrents` | Target folder where downloaded `.torrent` files are stored.                                                                             |

### Installation

Choose one of the following installation methods.

#### Install from PyPI (Recommended)

This method is best for using the package as a library or running the server without modifying the code.

1.  Install the package from PyPI:

```bash
pip install torrent-search-mcp
crawl4ai-setup # For crawl4ai/playwright
playwright install --with-deps chromium # If previous command fails
```

2.  Create a `.env` file in the directory where you'll run the application (optional).

3.  Run the MCP server (default: stdio):

```bash
python -m torrent_search
```

#### For Local Development

This method is for contributors who want to modify the source code.
Using [`uv`](https://github.com/astral-sh/uv):

1.  Clone the repository:

```bash
git clone https://github.com/philogicae/torrent-search-mcp.git
cd torrent-search-mcp
```

2.  Install dependencies using `uv`:

```bash
uv sync --frozen
uvx playwright install --with-deps chromium
```

3.  Create your configuration file by copying the example:

```bash
cp .env.example .env
```

4.  Run the MCP server (default: stdio):

```bash
uv run -m torrent_search
```

The repo also ships a `dev.sh` helper that locks/syncs deps, formats, lints, type-checks (`ty`) and runs the test suite with coverage:

```bash
./dev.sh
```

#### For Docker

This method uses Docker to run the server in a container.

`compose.yaml` is configured to bypass DNS issues (using [quad9](https://quad9.net/) DNS). The container runs the server in `http` (streamable-http) mode on port `8000` (endpoint `/mcp`) and persists downloaded torrent files to a named volume.

1.  Clone the repository (if you haven't already):

```bash
git clone https://github.com/philogicae/torrent-search-mcp.git
cd torrent-search-mcp
```

2.  Create your configuration file by copying the example:

```bash
cp .env.example .env
```

3.  Build and run the container using Docker Compose (default port: 8000):

```bash
docker compose up --build -d
```

4.  Access container logs:

```bash
docker logs torrent-search-mcp -f
```

## Usage

The package exposes a single entry point, `torrent-search-mcp` (installed by `pip`/`uvx`), equivalent to `python -m torrent_search`. It supports the following `--mode` values:

| Mode              | Endpoint | Description                                                                                                            |
| ----------------- | -------- | ---------------------------------------------------------------------------------------------------------------------- |
| `cli`             | —        | Run a single search query and print results to stdout.                                                                 |
| `stdio`           | —        | MCP server over stdio (default).                                                                                       |
| `http`            | `/mcp`   | MCP server using streamable HTTP (fastmcp's canonical HTTP alias).                                                     |
| `streamable-http` | `/mcp`   | Same as `http`; the modern, MCP-spec-recommended HTTP transport.                                                       |
| `sse`             | `/sse`   | MCP server using Server-Sent Events. Legacy HTTP transport (deprecated by the MCP spec in favor of `streamable-http`). |
| `fastapi`         | `/`      | Standalone FastAPI HTTP server (see [As FastAPI Server](#as-fastapi-server)).                                          |

Common flags (for `http`, `streamable-http`, `sse` and `fastapi` modes): `--host` (default `0.0.0.0`), `--port` (default `8000`), `--reload`, `--workers` (FastAPI only).

### As CLI

Run a one-off search directly from the terminal. Prints each result as `id (seeders|leechers|downloads) - filename`, then fetches the magnet/torrent for the top hit.

```bash
# Using the installed entry point
torrent-search-mcp --mode cli "breaking bad"

# Or via uvx without installing
uvx torrent-search-mcp --mode cli "breaking bad"

# Or from source
uv run -m torrent_search --mode cli "breaking bad"
```

### As Python Wrapper

```python
from torrent_search import torrent_search_api

results = await torrent_search_api.search_torrents("breaking bad")
for torrent in results:
    print(
        f"{torrent.filename} | {torrent.size} | {torrent.seeders} SE | {torrent.leechers} LE | {torrent.date} | {torrent.source}"
    )
```

`search_torrents` is async and accepts an optional `max_items` (default `10`). Each `Torrent` exposes `id`, `filename`, `size`, `seeders`, `leechers`, `date`, `source`, and (when available) `magnet_link` / `torrent_file`. Pass a torrent's `id` to `get_torrent()` to retrieve its magnet link or `.torrent` file path.

### As MCP Server

```python
from torrent_search import torrent_search_mcp

torrent_search_mcp.run(transport="sse")
```

### As FastAPI Server

This project also includes a FastAPI server as an alternative way to interact with the library via a standard HTTP API. This can be useful for direct API calls, integration with other web services, or for testing purposes.

**Running the FastAPI Server:**

```bash
# With Python
python -m torrent_search --mode fastapi
# With uv
uv run -m torrent_search --mode fastapi
```

- `--host <host>`: Default: `0.0.0.0`.
- `--port <port>`: Default: `8000`.
- `--reload`: Enables auto-reloading when code changes (useful for development).
- `--workers <workers>`: Default: `1`.

The FastAPI server will then be accessible at `http://<host>:<port>`.

**Available Endpoints:**
The FastAPI server exposes similar functionalities to the MCP server. Key endpoints include:

- `GET /`: Health check endpoint. Returns `{"status": "ok"}`.
- `POST /torrent/search`: Search for torrents. Query params: `query` (required) and `max_items` (optional, default `10`).
- `GET /torrent/{torrent_id}`: Get the magnet link or `.torrent` file for a specific torrent by id. Returns the magnet URI as text, or streams the `.torrent` file.
- `/docs`: Interactive API documentation (Swagger UI).
- `/redoc`: Alternative API documentation (ReDoc).

Environment variables are configured the same way as for the MCP server (via an `.env` file in the project root).

### Via MCP Clients

Usable with any MCP-compatible client. Available tools:

- `search_torrents(user_intent, query)`: Search for torrents across all available sources.
  - `user_intent`: A short description reflecting the user's overall intention (e.g. `"latest episode of Breaking Bad"`).
  - `query`: Optimized, lowercase, space-separated keywords (e.g. `"breaking bad s01e05"`). Generic/filler/technical terms should be stripped per the tool's docstring.
  - By default magnet links are stripped from the response to save tokens; set `INCLUDE_LINKS=true` to include them.
- `get_torrent(torrent_id)`: Get the magnet link or torrent file path for a specific torrent by id (the `id` returned by `search_torrents`).

Available resources:

- `data://torrent_sources`: Get the list of available torrent sources.

#### Example with Devin

Configuration:

```json
{
  "mcpServers": {
    ...
    # with stdio (only requires uv)
    "torrent-search-mcp": {
      "command": "uvx",
      "args": [ "torrent-search-mcp" ]
    },
    # with streamable-http transport (Docker default; requires running server)
    "torrent-search-mcp": {
      "serverUrl": "http://127.0.0.1:8000/mcp"
    },
    # with sse transport (legacy; requires running server)
    "torrent-search-mcp": {
      "serverUrl": "http://127.0.0.1:8000/sse"
    },
    ...
  }
}
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a history of changes to this project.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
