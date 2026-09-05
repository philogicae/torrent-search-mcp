# AGENTS.md

> **Audience.** AI agents working inside the torrent-search-mcp repository.

## Project overview

Torrent search MCP server — a Python-based torrent search service with MCP (Model Context Protocol) API, a static HTML frontend, and Telegram integration. 100% test coverage gate.

## Setup commands

- Lint/format: `uv run ruff format && uv run ruff check --fix`
- Typecheck: `uv run ty check`
- Tests (100% coverage gate): `uv run pytest -n 2 --dist worksteal --cov=torrent_search --cov-fail-under=100`
- Full local pipeline: `./dev.sh` (lock+sync, ruff, ty, prettier on md/html, tests with prettier before pytest — static HTML formatting matters because the served page is minified from it)
- Never run destructive docker commands against volumes (`torrent-search-data` holds auth tokens)
- Deploy: `docker compose up -d --build torrent-search-api torrent-search-mcp` (rebuild required for static changes; plain `restart` reuses the old image)

## Testing instructions

- 100% coverage gate enforced via `--cov-fail-under=100`.
- Test suite is hermetic against ambient env: autouse fixture pins `_PRUNE_MAGNET_LINKS=False` (uv auto-loads `.env`, which flipped module constants and broke assertions when a QA toggle lingered). (2026-08-27)
- `playwright-cli` verification standard: DOM snapshot + screenshot + console (+requests when network-relevant) recorded in TRACKING verification log with `.playwright-cli/` artifact paths (gitignored, local-only). (2026-08-27, R1-R4 logs populated)
- `approve.sh` — helper to approve a Web UI pairing code via `POST /telegram/auth/register` (see TRACKING.md).

## Security considerations

- [x] Session records older than 30 days are purged when the auth store loads; active tokens remain valid until logout or a later startup purge. (2026-08-28)
- [x] `/forward_telegram` is Bearer-session gated, rate-limited per chat (20/min), bot token never leaves server config. (2026-08-27)
- Accepted trade-off: pairing codes are 16-character alphanumeric strings; capacity-capped (50) and TTL-bounded (5 min).
- [x] Source-page links are retained only when they are absolute HTTP(S) URLs. (2026-08-30)

## Architecture backlog

### Backend

- [ ] `api_client.py` aiocache in-process only; multi-worker deployments (`--workers >1`) each keep their own cache/coalesce pool. Fine at current scale.
- [ ] `Torrent.format` id building relies on source strings being URL-safe enough for path params (`/torrent/{id}`); malformed sources could 404 confusingly.

### Frontend

- [ ] index.html is a single ~2.4k-line file with inline CSS/JS; extraction would help maintainability but costs the no-build pipeline. Keep single-file until it doubles again.
- [ ] Tile accordions on mobile rebuild all tiles on every breakpoint change (`mobileQuery` listener → full `render()`); acceptable at current list sizes.
- [x] `PRUNE_MAGNET_LINKS=true` prunes magnets on every Telegram path: forward popup draft (client, flag from `/telegram/session`) and `/forward_telegram` (server). Copy/magnet buttons keep originals. (2026-08-27)
- [x] Row actions share one `actionButtonsHtml()` renderer keyed on `session.enabled`: Telegram on → tg popup + copy magnet; off → magnet link + copy magnet (always 2 buttons, hit targets ~2rem). (2026-08-28)
- [x] Orbit spinner colors are theme vars (`--orbit-*`); light mode uses saturated ink rings, and hidden loaders no longer receive per-frame style writes. (2026-08-30)
- [x] Gate pointer effects stop outside the gate and avoid layout reads on every pointer event. (2026-08-30)

### MCP / API

- [ ] `_format_torrents` drops torrent ids when `INCLUDE_LINKS` unset? No — keeps ids; but magnet-less lines make `get_torrent` round trips required. Document this flow in README agent tips.

### Infra

- [x] Dockerfile lost `ENV PATH="/app/.venv/bin:$PATH"` in v4.1.0 refactor → container crash-looped (`exec torrent-search-mcp failed`). Restored. (2026-08-27)
- `Dockerfile.publish` — separate publish Dockerfile for PyPI-based images (`pip install torrent-search-mcp==$VERSION`).

### Performance

- [x] Single-flight coalescing added around cold search/popular misses (2026-08-27): concurrent identical requests share one scrape; sequential searches are intentionally uncached.
- [x] The 1337x popular parser applies `per_source` before fetching detail pages, avoiding unnecessary page requests. (2026-08-30)
- [ ] Popular endpoint awaits all sources on each cold call (hard cap 30s per source); consider per-source TTL caches so one slow source cannot hold back the complete response.

### Config & tooling

- [x] New env vars documented in `.env.example` + README: `TELEGRAM_BOT_TOKEN`, `PRUNE_MAGNET_LINKS` (default false), `TELEGRAM_AUTH_FILE`; stale `CRAWLER_IDLE_TIMEOUT` removed. (2026-08-27)
- Note: clipboard fallback must host its helper textarea inside an open `dialog[open]`; body siblings are inert while a modal dialog exists. All copy affordances share one `data-copy` dispatcher. (2026-08-27)
