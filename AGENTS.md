# AGENTS.md

> **Audience.** AI agents working inside the torrent-search-mcp repository.

## Project overview

Torrent search MCP server - a Python-based torrent search service with MCP (Model Context Protocol) API, a static HTML frontend, and Telegram integration. 100% test coverage gate.

## Setup commands

- Lint/format: `uv run ruff format && uv run ruff check --fix`
- Typecheck: `uv run ty check`
- Tests (100% coverage gate): `uv run pytest -n 2 --dist worksteal --cov=torrent_search --cov-fail-under=100`
- Full local pipeline: `./dev.sh` (lock+sync, ruff, ty, prettier on md/html, tests with prettier before pytest - static HTML formatting matters because the served page is minified from it)
- Never run destructive docker commands against volumes (`torrent-search-data` holds auth tokens)
- Deploy: `docker compose up -d --build torrent-search-api torrent-search-mcp` (rebuild required for static changes; plain `restart` reuses the old image)

## Testing instructions

- 100% coverage gate enforced via `--cov-fail-under=100`.
- Test suite is hermetic against ambient env: autouse fixture pins `_PRUNE_MAGNET_LINKS=False` (uv auto-loads `.env`, which flipped module constants and broke assertions when a QA toggle lingered). (2026-08-27)
- `playwright-cli` verification standard: DOM snapshot + screenshot + console (+requests when network-relevant) recorded in the verification log with `.playwright-cli/` artifact paths (gitignored, local-only).
- `approve.sh` - helper to approve a Web UI pairing code via `POST /telegram/auth/register`.

## Security considerations

- [x] Session records older than 30 days are purged when the auth store loads; active tokens remain valid until logout or a later startup purge. (2026-08-28)
- [x] `/forward_telegram` is Bearer-session gated, rate-limited per chat (20/min), bot token never leaves server config. (2026-08-27)
- Accepted trade-off: pairing codes are 16-character alphanumeric strings; capacity-capped (50) and TTL-bounded (5 min).
- [x] Source-page links are retained only when they are absolute HTTP(S) URLs. (2026-08-30)

## Conventions & constraints

- MCP protocol: FastMCP 4 (MCP SDK v2) serves the sessionless `2026-07-28` revision and negotiates older handshake revisions for legacy clients; direct HTTP calls use the `httpx2` drop-in (`httpx` is not installed).
- Frontend: `index.html` is intentionally a single file with inline CSS/JS and no build step (the served page is minified from it); keep it single-file until extraction is clearly justified.
- Clipboard: fallback helper textarea must be hosted inside an open `dialog[open]` (body siblings are inert while a modal dialog exists); all copy affordances share one `data-copy` dispatcher.
- Work tracking lives in Kaneo (project `torrent-search-mcp`, "Private Projects: Dev"); keep this file free of backlog checklists.
