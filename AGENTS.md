# AGENTS.md

> **Audience.** AI agents working inside the torrent-search-mcp repository.

## Project overview

Torrent search MCP server - a Python-based torrent search service with MCP (Model Context Protocol) API, a static HTML frontend, and Telegram integration.

- `torrent_search/mcp_server.py`: MCP tools (FastMCP) and the untrusted-data fencing of scraped output.
- `torrent_search/api_server.py`: REST API, Web UI hosting, Telegram auth and forward endpoints.
- `torrent_search/wrapper/parser.py`: per-source parsers (fetch + normalize to the shared CSV text pipeline).
- `torrent_search/wrapper/scraper.py`: `WEBSITES` registry, search/popular orchestration, per-source popular caches.
- `torrent_search/wrapper/api_client.py`: `TorrentSearchApi` facade used by the MCP tools and the CLI (caches, magnet resolution).
- `torrent_search/wrapper/models.py`: `Torrent` model, id/field validation. `telegram_auth.py`: session store, pairing challenges, rate limiter. `utils.py`: magnet pruning, encoding helpers.
- `torrent_search/static/index.html`: the whole frontend (inline CSS/JS, no build step; minified when served).

## Setup commands

- Lint/format: `uv run ruff format && uv run ruff check --fix`
- Typecheck: `uv run ty check`
- Tests (100% coverage gate): `uv run pytest -n 2 --dist worksteal --cov=torrent_search --cov-fail-under=100`
- Full local pipeline: `./dev.sh` (lock+sync, ruff, ty, prettier on md/html, then pytest - prettier runs before the tests because the served page is minified from `index.html`)
- Never run destructive docker commands against volumes (`torrent-search-data` holds auth tokens)
- Deploy: `docker compose up -d --build torrent-search-api torrent-search-mcp` (rebuild required for static changes; plain `restart` reuses the old image)

## Testing instructions

- 100% coverage gate enforced via `--cov-fail-under=100`; CI runs ruff/ty/pytest on push.
- Keep the suite hermetic against ambient env: the autouse `hermetic_env` fixture pins the Telegram/prune constants (`uv run` auto-loads `.env`, which otherwise flips module constants and breaks assertions).
- `playwright-cli` verification standard: DOM snapshot + screenshot + console (+requests when network-relevant) recorded in the verification log with `.playwright-cli/` artifact paths (gitignored, local-only).
- `approve.sh` - helper to approve a Web UI pairing code via `POST /telegram/auth/register`.

## Security considerations

- Scraped text is written by anonymous uploaders, so MCP output goes through `_wrap_untrusted()`: a per-response nonce fence plus a data-not-instructions notice. Any new tool returning scraped text must use it, and copies of the tag name inside the body must stay defanged.
- `/forward_telegram` is Bearer-session gated and rate-limited per chat (20/min); the Telegram bot token never leaves server config.
- Auth store bounds: sessions older than 30 days are purged at load only (an active session stays valid until logout or a later startup purge); pairing codes are 16-character alphanumeric, capacity-capped (50) and TTL-bounded (5 min) - accepted trade-off.
- Scraped source-page links are retained only when they are absolute HTTP(S) URLs.

## Conventions & constraints

- MCP protocol: FastMCP 4 (MCP SDK v2) serves the sessionless `2026-07-28` revision and negotiates older handshake revisions for legacy clients; direct HTTP calls use the `httpx2` drop-in (`httpx` is not installed).
- Frontend: `index.html` is intentionally a single file with inline CSS/JS and no build step (the served page is minified from it); keep it single-file until extraction is clearly justified.
- Clipboard: fallback helper textarea must be hosted inside an open `dialog[open]` (body siblings are inert while a modal dialog exists); all copy affordances share one `data-copy` dispatcher.
- Work tracking lives in Kaneo (project `torrent-search-mcp`, "Private Projects: Dev"); keep this file free of backlog checklists.
