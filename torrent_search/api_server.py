import logging
import secrets
from contextlib import asynccontextmanager
from functools import lru_cache
from os import getenv
from pathlib import Path as PathLib
from typing import Any

import httpx2
from fastapi import FastAPI, HTTPException, Path, Query, Request, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from minify_html import minify
from pydantic import BaseModel, Field, field_validator

from .wrapper import Torrent, TorrentSearchApi
from .wrapper.models import is_magnet_link
from .wrapper.parser import aclose_client
from .wrapper.telegram_auth import (
    SESSION_TTL_SECONDS,
    ChallengeManager,
    RateLimiter,
    TelegramAuthStore,
    new_session_token,
)
from .wrapper.utils import prune_magnet

logger = logging.getLogger("Torrent Search")

SESSION_COOKIE = "torrent_session"
_DOCS_PATHS = {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Close outbound HTTP clients on shutdown (connections are pooled)."""
    global _bot_client, _relay_client
    yield
    await aclose_client()
    if _bot_client is not None:
        await _bot_client.aclose()
        _bot_client = None
    if _relay_client is not None:
        await _relay_client.aclose()
        _relay_client = None


app = FastAPI(
    title="Torrent Search API",
    description="API server for Torrent Search API.",
    lifespan=_lifespan,
)
api_client = TorrentSearchApi()
app.add_middleware(GZipMiddleware, minimum_size=1024)
_STATIC_DIR = PathLib(__file__).parent / "static"
_TELEGRAM_BOT_HANDLE = getenv("TELEGRAM_BOT_HANDLE") or None
_TELEGRAM_BOT_TOKEN = getenv("TELEGRAM_BOT_TOKEN") or None
_TELEGRAM_AGENT_NAME = getenv("TELEGRAM_AGENT_NAME") or None
_TELEGRAM_MSG_FORWARD = getenv("TELEGRAM_MSG_FORWARD") or None
_AGENT_RELAY_URL = getenv("AGENT_RELAY_URL") or None
_AGENT_RELAY_TOKEN = getenv("AGENT_RELAY_TOKEN") or None
_AGENT_MODE = all((_AGENT_RELAY_URL, _AGENT_RELAY_TOKEN))
_PRUNE_MAGNET_LINKS = str(getenv("PRUNE_MAGNET_LINKS", "false")).strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
_REGISTER_SECRET = getenv("TORRENT_SEARCH_API_KEY") or None
_AUTH_STORE = TelegramAuthStore()
_CHALLENGES = ChallengeManager()
_CHALLENGE_LIMITER = RateLimiter(max_events=60, per_seconds=60)
_REGISTER_LIMITER = RateLimiter(max_events=30, per_seconds=60)
_POLL_LIMITER = RateLimiter(max_events=300, per_seconds=60)
_FORWARD_LIMITER = RateLimiter(max_events=20, per_seconds=60)
_SEARCH_LIMITER = RateLimiter(max_events=60, per_seconds=60)
_POPULAR_LIMITER = RateLimiter(max_events=30, per_seconds=60)
_GET_LIMITER = RateLimiter(max_events=120, per_seconds=60)
_bot_client: httpx2.AsyncClient | None = None


@lru_cache(maxsize=1)
def _webui_html() -> str:
    """Minify the single-file Web UI once, on first request."""
    return minify(
        (_STATIC_DIR / "index.html").read_text(encoding="utf-8"),
        minify_css=True,
        minify_js=True,
    )


@app.middleware("http")
async def _security_headers(request: Request, call_next: Any) -> Response:
    """Baseline browser hardening for the bundled UI and JSON API."""
    response: Response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
    )
    return response


def _gate_enabled() -> bool:
    """The pairing gate exists only when both the bot handle and secret are set."""
    return bool(_TELEGRAM_BOT_HANDLE and _REGISTER_SECRET)


@app.middleware("http")
async def _hide_docs_when_gated(request: Request, call_next: Any) -> Response:
    """Expose the OpenAPI schema only to an authenticated owner."""
    if (
        _gate_enabled()
        and request.url.path in _DOCS_PATHS
        and not (
            _is_server_token(_bearer_token(request)) or _authenticated_token(request)
        )
    ):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    return await call_next(request)


def _bot() -> httpx2.AsyncClient:
    global _bot_client
    if _bot_client is None:
        _bot_client = httpx2.AsyncClient(
            base_url="https://api.telegram.org", timeout=15
        )
    return _bot_client


_relay_client: httpx2.AsyncClient | None = None


def _relay() -> httpx2.AsyncClient:
    global _relay_client
    if _relay_client is None:
        _relay_client = httpx2.AsyncClient(timeout=15)
    return _relay_client


app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


def _no_store(response: Response) -> None:
    response.headers.update(
        {
            "Cache-Control": "no-cache, no-store",
            "Pragma": "no-cache",
            "Expires": "0",
        }
    )


@app.get(
    "/",
    summary="Web UI",
    tags=["Webui"],
)
async def webui() -> Response:
    """
    Serve the bundled web UI. Always re-fetched: the page is a thin client
    over the API and must never run stale markup against a fresh server.
    """
    return Response(
        content=_webui_html(),
        media_type="text/html",
        headers={"Cache-Control": "no-cache, no-store"},
    )


@app.get("/sources", summary="List Sources", tags=["General"], response_model=list[str])
async def list_sources() -> list[str]:
    """
    Endpoint listing the available torrent sources.
    """
    return api_client.available_sources()


@app.get(
    "/torrent/popular",
    summary="Popular Torrents",
    tags=["Torrents"],
    response_model=list[Torrent],
)
async def popular_torrents(
    response: Response,
    request: Request,
    per_source: int = Query(20, ge=1, le=200),
    refresh: bool = False,
) -> list[Torrent]:
    """
    Get the most popular torrents across sources with a top listing,
    keeping up to `per_source` results from each. Cached server-side for
    5 minutes; the response is marked no-store so browsers always re-fetch.
    `refresh=true` drops the server-side caches and asks every source for a
    fresh listing (the Web UI POPULAR button uses it).
    Corresponds to `TorrentSearchApi.popular_torrents()`.
    """
    if not _POPULAR_LIMITER.allow(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many popular requests.")
    _require_torrent_access(request)
    _no_store(response)
    torrents: list[Torrent] = await api_client.popular_torrents(per_source, refresh)
    return torrents


@app.post(
    "/torrent/search",
    summary="Search Torrents",
    tags=["Torrents"],
    response_model=list[Torrent],
)
async def search_torrents(
    response: Response,
    request: Request,
    query: str = Query(..., min_length=1, max_length=200),
    max_items: int | None = Query(None, ge=1, le=200),
    per_source: int | None = Query(None, ge=1, le=200),
) -> list[Torrent]:
    """
    Search for torrents across all enabled sources.

    `max_items` caps the total number of results (defaults to 20 when
    `per_source` is unset). When `per_source` is given, up to that many
    results are kept per source (ranked by swarm health) so providers are
    spread instead of a global cap only; the total is then uncapped unless
    `max_items` is passed too.
    Corresponds to `TorrentSearchApi.search_torrents()`.
    """
    if not _SEARCH_LIMITER.allow(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many searches.")
    _require_torrent_access(request)
    _no_store(response)
    effective_max = max_items
    if effective_max is None and per_source is None:
        effective_max = 20
    torrents: list[Torrent] = await api_client.search_torrents(
        query, effective_max, per_source
    )
    return torrents


@app.get(
    "/torrent/{torrent_id}",
    summary="Get Magnet Link",
    tags=["Torrents"],
    response_model=str,
)
async def get_torrent(
    request: Request,
    response: Response,
    torrent_id: str = Path(..., description="The ID of the torrent.", max_length=1024),
) -> str:
    """
    Get the magnet link for a specific torrent by id.
    Corresponds to `TorrentSearchApi.get_torrent()`.
    """
    if not _GET_LIMITER.allow(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many magnet lookups.")
    _require_torrent_access(request)
    _no_store(response)
    result: str | None = await api_client.get_torrent(torrent_id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail="Magnet link not found.",
        )
    return result


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _bearer_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    if authorization[:7].lower() == "bearer ":
        return authorization[7:].strip()
    return ""


def _cookie_secure(request: Request) -> bool:
    override = getenv("COOKIE_SECURE")
    if override is not None:
        return override.strip().lower() in {"1", "true", "yes", "on"}
    forwarded = request.headers.get("x-forwarded-proto", "")
    proto = forwarded.split(",", 1)[0].strip().lower()
    return request.url.scheme == "https" or proto == "https"


def _set_session_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=SESSION_TTL_SECONDS,
        path="/",
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(request),
    )


def _authenticated_token(request: Request) -> str | None:
    """Return the first valid session token from Bearer or the HttpOnly cookie."""
    candidates = (_bearer_token(request), request.cookies.get(SESSION_COOKIE, ""))
    for token in candidates:
        if token and _AUTH_STORE.chat_id_for_token(token) is not None:
            return token
    return None


def _is_server_token(token: str) -> bool:
    return (
        bool(token)
        and bool(_REGISTER_SECRET)
        and secrets.compare_digest(token, _REGISTER_SECRET)
    )


def _is_authenticated(request: Request) -> bool:
    return _authenticated_token(request) is not None


def _require_torrent_access(request: Request) -> None:
    """Gate torrent endpoints when the Web UI pairing gate is enabled.

    Browser clients present their HttpOnly session cookie (or a legacy Bearer
    token); the MCP server (and other server-to-server callers) present
    ``TORRENT_SEARCH_API_KEY``. When the Telegram integration is off there is
    no gate, so the API stays open like the Web UI.
    """
    if not _gate_enabled():
        return
    if _is_server_token(_bearer_token(request)) or _authenticated_token(request):
        return
    raise HTTPException(status_code=401, detail="Valid session required.")


@app.get(
    "/telegram/session",
    summary="Telegram Session",
    tags=["Telegram"],
)
async def telegram_session(request: Request, response: Response) -> dict[str, object]:
    """
    Auth state for the Web UI (send the session token as a Bearer header).
    The bot handle is public (it is required to build the pairing deep
    links); session tokens are what gate the app.
    """
    response.headers["Cache-Control"] = "no-store"
    enabled = _gate_enabled()
    authenticated = enabled and _is_authenticated(request)
    if enabled and authenticated:
        # Migrate existing localStorage Bearer sessions to the HttpOnly cookie
        # so the browser keeps access even if the original tab is closed.
        bearer = _bearer_token(request)
        if bearer and _authenticated_token(request) == bearer:
            _set_session_cookie(response, request, bearer)
    elif enabled and request.cookies.get(SESSION_COOKIE):
        # Stale/revoked cookie on a return visit: clear it so the browser does
        # not keep presenting a dead session.
        response.delete_cookie(SESSION_COOKIE, path="/")
    return {
        "enabled": enabled,
        "authenticated": authenticated or not enabled,
        "handle": _TELEGRAM_BOT_HANDLE,
        "prune_magnet_links": _PRUNE_MAGNET_LINKS,
        "agent_name": _TELEGRAM_AGENT_NAME if _AGENT_MODE else None,
    }


@app.post(
    "/telegram/auth/challenge",
    summary="Create Pairing Code",
    tags=["Telegram"],
)
async def telegram_challenge(request: Request, response: Response) -> dict[str, object]:
    """
    Generate a one-time pairing code shown in the Web UI gate. The code must
    be approved via the register endpoint (or the authorize_webapp MCP tool,
    bound to a Telegram chat id) before it grants a session token.
    """
    if _TELEGRAM_BOT_HANDLE is None or not _REGISTER_SECRET:
        raise HTTPException(status_code=404, detail="Telegram pairing disabled.")
    if not _CHALLENGE_LIMITER.allow(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many pairing attempts.")
    code, ttl = _CHALLENGES.create()
    logger.info(
        "Pairing challenge created from %s (ttl=%.0fs).", _client_ip(request), ttl
    )
    response.headers["Cache-Control"] = "no-store"
    return {"code": code, "expires_in": ttl}


@app.get(
    "/telegram/auth/poll",
    summary="Poll Pairing Code",
    tags=["Telegram"],
)
async def telegram_poll(
    request: Request, response: Response, code: str
) -> dict[str, str]:
    """
    Poll a pairing code while waiting for approval. When the code has been
    approved it is consumed here: the response carries the one-time session
    token (stored by the browser) bound to the registrant's chat id.
    """
    if not _POLL_LIMITER.allow(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many polls.")
    response.headers["Cache-Control"] = "no-store"
    status = _CHALLENGES.poll(code)
    if status == "approved":
        chat_id = _CHALLENGES.consume(code)
        if chat_id is not None:
            token = new_session_token()
            _AUTH_STORE.add_session(chat_id, token)
            _set_session_cookie(response, request, token)
            logger.info("Telegram session granted to chat %s.", chat_id)
            return {"status": "approved", "token": token}
        # Another poll consumed it (or it expired between poll and consume):
        # never report "approved" without a token.
        status = "expired"
    return {"status": status}


@app.delete(
    "/telegram/auth/challenge/{code}",
    summary="Cancel Pairing Code",
    tags=["Telegram"],
)
async def telegram_cancel(
    code: str = Path(..., description="The pairing code."),
) -> dict[str, str]:
    """Drop a pending pairing code (Web UI popup closed before approval)."""
    _CHALLENGES.cancel(code)
    return {"status": "cancelled"}


@app.post(
    "/telegram/auth/register",
    summary="Approve Pairing Code",
    tags=["Telegram"],
)
async def telegram_register(
    request: Request, code: str, chat_id: str
) -> dict[str, str]:
    """
    Approve a pending pairing code and bind it to the owner's Telegram chat
    id. Requires the ``TORRENT_SEARCH_API_KEY`` bearer; without the secret
    configured the endpoint is disabled entirely.
    """
    if not _REGISTER_SECRET:
        raise HTTPException(
            status_code=403,
            detail="Registration disabled: TORRENT_SEARCH_API_KEY is not configured.",
        )
    authorization = _bearer_token(request)
    if not _is_server_token(authorization):
        raise HTTPException(status_code=401, detail="Invalid registrar secret.")
    if not _REGISTER_LIMITER.allow(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many registrations.")
    if not _CHALLENGES.approve(code, chat_id):
        raise HTTPException(status_code=404, detail="Unknown or expired pairing code.")
    logger.info("Pairing code approved for chat %s.", chat_id)
    return {"status": "approved"}


@app.post(
    "/telegram/auth/logout",
    summary="Telegram Logout",
    tags=["Telegram"],
)
async def telegram_logout(request: Request, response: Response) -> dict[str, str]:
    """Revoke the presented session token(s) and clear the session cookie."""
    tokens = {
        token
        for token in (
            _bearer_token(request),
            request.cookies.get(SESSION_COOKIE, ""),
        )
        if token
    }
    revoked = any(_AUTH_STORE.remove_token(token) for token in tokens)
    response.delete_cookie(SESSION_COOKIE, path="/")
    if revoked:
        logger.info("Telegram session revoked via logout.")
    return {"status": "logged_out"}


class ForwardPayload(BaseModel):
    """Torrent info accepted by ``/forward_telegram``."""

    filename: str = Field(min_length=1, max_length=512)
    magnet_link: str = Field(min_length=1, max_length=4096)
    size: str | None = Field(None, max_length=64)
    seeders: int | None = Field(None, ge=0)

    @field_validator("magnet_link")
    @classmethod
    def validate_magnet_link(cls, value: str) -> str:
        if not is_magnet_link(value):
            raise ValueError("a magnet URI with a btih info hash is required")
        return value


@app.post(
    "/forward_telegram",
    summary="Forward Torrent To Telegram",
    tags=["Telegram"],
)
async def forward_telegram(request: Request, payload: ForwardPayload) -> dict[str, str]:
    """
    Send a torrent to a Telegram chat.

    Browser clients authenticate with their session token and send to the
    chat bound to it. Server-to-server callers (the MCP server) authenticate
    with ``TORRENT_SEARCH_API_KEY`` and must pass the target ``chat_id``
    query param. When ``PRUNE_MAGNET_LINKS`` is enabled the forwarded magnet
    is pruned to ``magnet:?xt=urn:btih:HASH&dn=<filename>``; otherwise the
    original magnet (trackers included) is sent as-is. In agent mode
    (``AGENT_RELAY_URL`` plus ``AGENT_RELAY_TOKEN``) the torrent is POSTed to
    the agent's HTTP relay instead of the Telegram Bot API (bots never
    receive bot-authored Telegram messages); ``TELEGRAM_AGENT_NAME`` and
    ``TELEGRAM_MSG_FORWARD`` provide the relay sender and notice.
    """
    bearer = _bearer_token(request)
    server_forward = _is_server_token(bearer)
    session_token = _authenticated_token(request)
    chat_id = _AUTH_STORE.chat_id_for_token(session_token) if session_token else None
    if server_forward:
        chat_id = request.query_params.get("chat_id", "").strip() or None
    if not _TELEGRAM_BOT_TOKEN and not _AGENT_MODE:
        raise HTTPException(
            status_code=503,
            detail="Telegram forwarding disabled: TELEGRAM_BOT_TOKEN not configured.",
        )
    if not chat_id:
        if server_forward:
            raise HTTPException(
                status_code=400,
                detail="chat_id query param is required for server-to-server forwards.",
            )
        raise HTTPException(status_code=401, detail="Valid session required.")
    if not _FORWARD_LIMITER.allow(chat_id):
        raise HTTPException(status_code=429, detail="Too many forwards.")
    magnet = (
        prune_magnet(payload.magnet_link, payload.filename)
        if _PRUNE_MAGNET_LINKS
        else payload.magnet_link
    )
    if _AGENT_MODE:
        try:
            relay_response = await _relay().post(
                _AGENT_RELAY_URL or "",
                json={
                    "chat_id": chat_id,
                    "sender": _TELEGRAM_AGENT_NAME or "TorrentSearch",
                    "notice": _TELEGRAM_MSG_FORWARD or "",
                    "prompt": f"Download this torrent: {magnet}",
                },
                headers={"X-Relay-Token": _AGENT_RELAY_TOKEN or ""},
            )
            relay_response.raise_for_status()
        except Exception as e:
            logger.warning("Agent relay failed for chat %s: %s", chat_id, e)
            raise HTTPException(status_code=502, detail="Agent relay failed.") from e
        logger.info("Torrent forwarded to agent for chat %s.", chat_id)
        return {"status": "sent"}
    lines = [f"🐋 {payload.filename}"]
    if payload.size:
        lines.append(f"Size: {payload.size}")
    if payload.seeders is not None:
        lines.append(f"Seeders: {payload.seeders}")
    text = "\n".join([*lines, magnet])
    if len(text) > 4096:
        raise HTTPException(
            status_code=413,
            detail="Forwarded message is too long for Telegram (4096 chars).",
        )
    try:
        bot_response = await _bot().post(
            f"/bot{_TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": True,
            },
        )
        bot_response.raise_for_status()
        data = bot_response.json()
        if not data.get("ok"):
            raise ValueError(str(data.get("description", "unknown error")))
    except Exception as e:
        logger.warning("Telegram forward failed for chat %s: %s", chat_id, e)
        raise HTTPException(status_code=502, detail="Telegram send failed.") from e
    logger.info("Torrent forwarded to chat %s.", chat_id)
    return {"status": "sent"}
