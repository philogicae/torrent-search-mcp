# Torrent Search MCP Server & API

[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://docs.astral.sh/uv/getting-started/installation/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![PyPI](https://badge.fury.io/py/torrent-search-mcp.svg?cache-control=no-cache)](https://badge.fury.io/py/torrent-search-mcp)
[![Actions status](https://github.com/philogicae/torrent-search-mcp/actions/workflows/python-package-ci.yml/badge.svg?cache-control=no-cache)](https://github.com/philogicae/torrent-search-mcp/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/philogicae/torrent-search-mcp)

This repository provides a Python API and an MCP (Model Context Protocol) server to find torrents programmatically on ThePirateBay, Nyaa and YggTorrent. It allows for easy integration into other applications or services.

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

-   API wrapper for ThePirateBay, Nyaa and YggTorrent.
    -   **Your Ygg passkey is injected locally into the torrent file/magnet link, ensuring it's not exposed externally**
-   MCP server interface for standardized communication (stdio, sse, streamable-http)
-   FastAPI server interface for alternative HTTP access (e.g., for direct API calls or testing)
-   Tools:
    -   Search for torrents on ThePirateBay, Nyaa and YggTorrent
    -   Get details for a specific YGG torrent
    -   Retrieve YGG magnet links

## Setup

### Prerequisites

-   An active YggTorrent account and passkey (Optional).
-   Python 3.10+ (required for PyPI install).
-   [`uv`](https://github.com/astral-sh/uv) (for local development)
-   Docker and Docker Compose (for Docker setup)

### Configuration (Optional)

This application requires your YggTorrent passkey to interact with the API.

1.  **Find your Passkey**: On the YggTorrent website, navigate to `Mon compte` -> `Mes paramètres`. Your passkey is part of the tracker URL, which looks like `http://tracker.p2p-world.net:8080/{YOUR_PASSKEY}/announce`.

2.  **Set Environment Variable**: The application reads the passkey from the `YGG_PASSKEY` environment variable. The recommended way to set this is by creating a `.env` file in your project's root directory. The application will load it automatically.

### Installation

Choose one of the following installation methods.

#### Install from PyPI (Recommended)

This method is best for using the package as a library or running the server without modifying the code.

1.  Install the package from PyPI:
```bash
pip install torrent-search-mcp
crawl4ai-setup # For crawl4ai/playwright
uvx playwright install # If previous command fails
```
2.  Create a `.env` file in the directory where you'll run the application and add your passkey (optional):
```env
YGG_PASSKEY=your_passkey_here
```
3.  Run the MCP server (default port: 8000):
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
uv sync
crawl4ai-setup # For crawl4ai/playwright
uvx playwright install # If previous command fails
```
3.  Create your configuration file by copying the example and add your passkey (optional):
```bash
cp .env.example .env
```

4.  Run the MCP server (default port: 8000):
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

3.  Build and run the container using Docker Compose (default port: 8765):
```bash
docker-compose -f docker/compose.yaml up --build [-d]
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

This project also includes a FastAPI server as an alternative way to interact with the YggTorrent functionalities via a standard HTTP API. This can be useful for direct API calls, integration with other web services, or for testing purposes.

**Running the FastAPI Server:**
```bash
# Dev
python -m torrent_search --fastapi
# Prod
uvicorn torrent_search.fastapi_server:app
```
- `--host <host>`: Default: `0.0.0.0`.
- `--port <port>`: Default: `8000`.
- `--reload`: Enables auto-reloading when code changes (useful for development).
- `--workers <workers>`: Default: `1`.

The FastAPI server will then be accessible at `http://<host>:<port>`

**Available Endpoints:**
The FastAPI server exposes similar functionalities to the MCP server. Key endpoints include:
- `/`: A simple health check endpoint. Returns `{"status": "ok"}`.
- `/docs`: Interactive API documentation (Swagger UI).
- `/redoc`: Alternative API documentation (ReDoc).

Environment variables (like `YGG_PASSKEY`) are configured the same way as for the MCP server (via an `.env` file in the project root).

### Via MCP Clients

Usable with any MCP-compatible client. Available tools:

-   `search_torrents`: Search for torrents.
-   `get_torrent_details`: Get details of a specific torrent.
-   `get_magnet_link`: Get the magnet link for a torrent.

#### Example with Windsurf
Configuration:
```json
{
  "mcpServers": {
    ...
    # with stdio (only requires uv)
    "mcp-torrent-search": {
      "command": "uvx",
      "args": [ "torrent-search-mcp" ],
      "env": { "YGG_PASSKEY": "your_passkey_here" } # optional
    },
    # with sse transport (requires installation)
    "mcp-torrent-search": {
      "serverUrl": "http://127.0.0.1:8000/sse"
    },
    # with streamable-http transport (requires installation)
    "mcp-torrent-search": {
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