FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app
# Install dependencies
COPY pyproject.toml uv.lock README.md /app/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev
# Install project
COPY torrent_search /app/torrent_search
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev
EXPOSE 8000
CMD ["torrent-search-mcp", "--mode", "http"]