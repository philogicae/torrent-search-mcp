#!/bin/bash
set -e

# Lock and sync dependencies
uv lock && uv sync -U --link-mode=copy

# Format code
uv run ruff format

# Check for linting errors
uv run ruff check --fix

# Run type checking
uv run ty check

# Run tests
uv run pytest