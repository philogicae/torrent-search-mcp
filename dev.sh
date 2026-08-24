#!/bin/bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Python tooling
# ---------------------------------------------------------------------------

echo "==> Locking and syncing dependencies"
uv lock && uv sync -U --link-mode=copy

echo "==> Formatting Python code"
uv run ruff format

echo "==> Linting Python code (with autofix)"
uv run ruff check --fix

echo "==> Type checking"
uv run ty check

# ---------------------------------------------------------------------------
# Markdown / HTML checks (config)
# ---------------------------------------------------------------------------

MISC_DIRS=("./torrent_search/static")

echo "==> Formatting markdown and html files"
npx --yes prettier --write --print-width 200 --log-level warn "${MISC_DIRS[*]/%//**/*.{md,html}}" ./*.md

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

echo "==> Running tests with coverage (parallel)"
uv run pytest -n 2 --dist worksteal --cov=torrent_search --cov-report=term-missing
