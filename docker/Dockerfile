FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project --no-cache --no-editable

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
RUN apt-get update && \
    uvx playwright install --with-deps chromium && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
COPY pyproject.toml uv.lock README.md ./
COPY torrent_search/ ./torrent_search/

EXPOSE 8000

CMD ["uv", "run", "-m", "torrent_search", "--mode", "sse"]
#CMD ["uv", "run", "-m", "torrent_search", "--mode", "streamable-http"]