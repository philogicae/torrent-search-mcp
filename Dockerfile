FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS runner
ENV UV_PYTHON_DOWNLOADS=0

# Install playwright dependencies
RUN apt-get update && \
    uvx playwright install --with-deps chromium && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app

# Install dependencies
COPY pyproject.toml uv.lock README.md /app/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

# Install project
COPY torrent_search /app/torrent_search
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

FROM runner
COPY --from=builder --chown=app:app /app /app
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
CMD ["torrent-search-mcp", "--mode", "sse"]