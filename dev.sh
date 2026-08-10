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
# Tests
# ---------------------------------------------------------------------------

echo "==> Running tests with coverage (parallel)"
uv run pytest -n 3 --dist worksteal --cov=torrent_search --cov-report=term-missing
