FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim
RUN apt-get update && \
    uvx playwright install --with-deps chromium && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-editable
COPY torrent_search/ ./torrent_search/

EXPOSE 8000

CMD ["uv", "run", "--locked", "--no-sync", "-m", "torrent_search", "--mode", "sse"]