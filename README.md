# Torrent Search MCP Server & API

[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://docs.astral.sh/uv/getting-started/installation/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![PyPI](https://badge.fury.io/py/torrent-search-mcp.svg?cache-control=no-cache)](https://badge.fury.io/py/torrent-search-mcp)
[![Actions status](https://github.com/philogicae/torrent-search-mcp/actions/workflows/python-package-ci.yml/badge.svg?cache-control=no-cache)](https://github.com/philogicae/torrent-search-mcp/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/philogicae/torrent-search-mcp)

This repository provides a Python API and an MCP (Model Context Protocol) server to find torrents programmatically on ThePirateBay, Nyaa, YggTorrent and La Cale. It allows for easy integration into other applications or services.

<a href="https://glama.ai/mcp/servers/@philogicae/torrent-search-mcp">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/@philogicae/torrent-search-mcp/badge?cache-control=no-cache" alt="Torrent Search MCP server" />
</a>

## Quickstart

> [How to use it with MCP Clients](#via-mcp-clients)

> [Run it with Docker to bypass common DNS issues](#for-docker)

## Table of Contents

- [Features](#features)
- [Setup](#setup)
  - [Prerequisites](#prerequisites)
  - [Configuration](#configuration-optional)
  - [Installation](#installation)
    - [Install from PyPI (Recommended)](#install-from-pypi-recommended)
    - [For Local Development](#for-local-development)
    - [For Docker](#for-docker)
- [Usage](#usage)
  - [As Python Wrapper](#as-python-wrapper)
  - [As MCP Server](#as-mcp-server)
  - [As FastAPI Server](#as-fastapi-server)
  - [Via MCP Clients](#via-mcp-clients)
    - [Example with Windsurf](#example-with-windsurf)
- [Contributing](#contributing)
- [Changelog](#changelog)
- [License](#license)

## Features

- API wrapper for ThePirateBay, Nyaa, YggTorrent and La Cale.
- MCP server interface for standardized communication (stdio, sse, streamable-http)
- FastAPI server interface for alternative HTTP access (e.g., for direct API calls or testing)
- Tools:
  - Search for torrents across all available sources
  - Get magnet link or torrent file for a specific torrent by id

## Setup

### Prerequisites

- An active YggTorrent account with username and password (Optional).
- An active La Cale account with passkey (Optional).
- Python 3.10+ (required for PyPI install).
- [`uv`](https://github.com/astral-sh/uv) (for local development)
- Chromium and its required dependencies
- Docker and Docker Compose (for Docker setup)

### Configuration (Optional)

This application requires credentials if you want to interact with YggTorrent or La Cale.

1.  **YggTorrent**: Username and password from your account.
2.  **La Cale**: Find your passkey on the La Cale website at `https://la-cale.space/profile`.
3.  **Set Environment Variables**: The application reads configuration from environment variables. The recommended way to set them is by creating a `.env` file in your project's root directory. The application will load it automatically. See `.env.example` for all available options.

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

2.  Create a `.env` file in the directory where you'll run the application and add your credentials (optional):

```env
YGG_USERNAME=your_username_here
YGG_PASSWORD=your_password_here
LA_CALE_PASSKEY=your_passkey_here
```

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
uv sync --locked
uvx playwright install --with-deps chromium
```

3.  Create your configuration file by copying the example and add your credentials (optional):

```bash
cp .env.example .env
```

4.  Run the MCP server (default: stdio):

```bash
uv run -m torrent_search
```

#### For Docker

This method uses Docker to run the server in a container.

compose.yaml is configured to bypass DNS issues (using [quad9](https://quad9.net/) DNS).

1.  Clone the repository (if you haven't already):

```bash
git clone https://github.com/philogicae/torrent-search-mcp.git
cd torrent-search-mcp
```

2.  Create your configuration file by copying the example and add your passkey (optional):

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

### As Python Wrapper

```python
from torrent_search import torrent_search_api

results = torrent_search_api.search_torrents('...')
for torrent in results:
    print(f"{torrent.filename} | {torrent.size} | {torrent.seeders} SE | {torrent.leechers} LE | {torrent.date} | {torrent.source}")
```

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

The FastAPI server will then be accessible at `http://<host>:<port>`

**Available Endpoints:**
The FastAPI server exposes similar functionalities to the MCP server. Key endpoints include:

- `/`: A simple health check endpoint. Returns `{"status": "ok"}`.
- `/torrent/search`: Search for torrents (POST request with `query` and optional `max_items` parameters).
- `/torrent/{torrent_id}`: Get magnet link or torrent file for a specific torrent by id.
- `/docs`: Interactive API documentation (Swagger UI).
- `/redoc`: Alternative API documentation (ReDoc).

Environment variables (like `YGG_USERNAME`, `YGG_PASSWORD`, `LA_CALE_PASSKEY`) are configured the same way as for the MCP server (via an `.env` file in the project root).

### Via MCP Clients

Usable with any MCP-compatible client. Available tools:

- `search_torrents`: Search for torrents across all available sources (ThePirateBay, Nyaa, YggTorrent, La Cale).
- `get_torrent`: Get the magnet link or torrent file for a specific torrent by id.

Available resources:

- `data://torrent_sources`: Get the list of available torrent sources.

#### Example with Windsurf

Configuration:

```json
{
  "mcpServers": {
    ...
    # with stdio (only requires uv)
    "torrent-search-mcp": {
      "command": "uvx",
      "args": [ "torrent-search-mcp" ],
      "env": {
        "YGG_LOCAL_API": "http://localhost:3456", # YggTorrent instance URL
        "LA_CALE_PASSKEY": "your_passkey_here" # La Cale passkey
      } # optional
    },
    # with sse transport (requires installation)
    "torrent-search-mcp": {
      "serverUrl": "http://127.0.0.1:8000/sse"
    },
    # with streamable-http transport (requires installation)
    "torrent-search-mcp": {
      "serverUrl": "http://127.0.0.1:8000/mcp" # not yet supported by every client
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
