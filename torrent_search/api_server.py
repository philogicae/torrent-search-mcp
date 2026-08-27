import logging
import secrets
from os import getenv
from pathlib import Path as PathLib

import httpx
from fastapi import FastAPI, HTTPException, Path, Request, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from minify_html import minify
from pydantic import BaseModel

from .wrapper import Torrent, TorrentSearchApi
from .wrapper.telegram_auth import (
    ChallengeManager,
    RateLimiter,
    TelegramAuthStore,
    new_session_token,
)
from .wrapper.utils import prune_magnet

logger = logging.getLogger("Torrent Search")

app = FastAPI(
    title="Torrent Search API",
    description="API server for Torrent Search API.",
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
_WEBUI_HTML = minify(
    (_STATIC_DIR / "index.html").read_text(encoding="utf-8"),
    minify_css=True,
    minify_js=True,
)
_AUTH_STORE = TelegramAuthStore()
_CHALLENGES = ChallengeManager()
_CHALLENGE_LIMITER = RateLimiter(max_events=5, per_seconds=60)
_REGISTER_LIMITER = RateLimiter(max_events=10, per_seconds=60)
_POLL_LIMITER = RateLimiter(max_events=60, per_seconds=60)
_FORWARD_LIMITER = RateLimiter(max_events=20, per_seconds=60)
_bot_client: httpx.AsyncClient | None = None


def _bot() -> httpx.AsyncClient:
    global _bot_client
    if _bot_client is None:
        _bot_client = httpx.AsyncClient(base_url="https://api.telegram.org", timeout=15)
    return _bot_client


_relay_client: httpx.AsyncClient | None = None


def _relay() -> httpx.AsyncClient:
    global _relay_client
    if _relay_client is None:
        _relay_client = httpx.AsyncClient(timeout=15)
    return _relay_client


app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


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
        content=_WEBUI_HTML,
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
async def popular_torrents(response: Response, per_source: int = 20) -> list[Torrent]:
    """
    Get the most popular torrents across sources with a top listing,
    keeping up to `per_source` results from each. Cached server-side for
    2 minutes; the response is marked no-store so browsers always re-fetch.
    Corresponds to `TorrentSearchApi.popular_torrents()`.
    """
    response.headers.update(
        {
            "Cache-Control": "no-cache, no-store",
            "Pragma": "no-cache",
            "Expires": "0",
        }
    )
    torrents: list[Torrent] = await api_client.popular_torrents(per_source)
    return torrents


@app.post(
    "/torrent/search",
    summary="Search Torrents",
    tags=["Torrents"],
    response_model=list[Torrent],
)
async def search_torrents(
    response: Response,
    query: str,
    max_items: int = 20,
) -> list[Torrent]:
    """
    Search for torrents across all enabled sources.
    Corresponds to `TorrentSearchApi.search_torrents()`.
    """
    response.headers.update(
        {
            "Cache-Control": "no-cache, no-store",
            "Pragma": "no-cache",
            "Expires": "0",
        }
    )
    torrents: list[Torrent] = await api_client.search_torrents(query, max_items)
    return torrents


@app.get(
    "/torrent/{torrent_id}",
    summary="Get Magnet Link",
    tags=["Torrents"],
    response_model=str,
)
async def get_torrent(
    torrent_id: str = Path(..., description="The ID of the torrent."),
) -> str:
    """
    Get the magnet link for a specific torrent by id.
    Corresponds to `TorrentSearchApi.get_torrent()`.
    """
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
    return authorization[7:].strip() if authorization.startswith("Bearer ") else ""


def _is_authenticated(request: Request) -> bool:
    token = _bearer_token(request)
    return bool(token) and _AUTH_STORE.chat_id_for_token(token) is not None


@app.get(
    "/telegram/session",
    summary="Telegram Session",
    tags=["Telegram"],
)
async def telegram_session(request: Request) -> dict[str, object]:
    """
    Auth state for the Web UI (send the session token as a Bearer header).
    The bot handle is public (it is required to build the pairing deep
    links); session tokens are what gate the app.
    """
    enabled = _TELEGRAM_BOT_HANDLE is not None
    authenticated = enabled and _is_authenticated(request)
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
            logger.info("Telegram session granted to chat %s.", chat_id)
            return {"status": "approved", "token": token}
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
    authorization = request.headers.get("authorization", "")
    expected = f"Bearer {_REGISTER_SECRET}"
    if not secrets.compare_digest(authorization, expected):
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
async def telegram_logout(request: Request) -> dict[str, str]:
    """Revoke the presented session token (removed from the server store)."""
    token = _bearer_token(request)
    revoked = bool(token) and _AUTH_STORE.remove_token(token)
    if revoked:
        logger.info("Telegram session revoked via logout.")
    return {"status": "logged_out"}


class ForwardPayload(BaseModel):
    """Torrent info accepted by ``/forward_telegram``."""

    filename: str
    magnet_link: str
    size: str | None = None
    seeders: int | None = None


@app.post(
    "/forward_telegram",
    summary="Forward Torrent To Telegram",
    tags=["Telegram"],
)
async def forward_telegram(request: Request, payload: ForwardPayload) -> dict[str, str]:
    """
    Send a torrent to the Telegram chat bound to the browser's session token.
    When ``PRUNE_MAGNET_LINKS`` is enabled the forwarded magnet is pruned to
    ``magnet:?xt=urn:btih:HASH&dn=<filename>``; otherwise the original magnet
    (trackers included) is sent as-is. In agent mode (``AGENT_RELAY_URL`` plus
    ``AGENT_RELAY_TOKEN``) the torrent is POSTed to the agent's HTTP relay
    instead of the Telegram Bot API (bots never receive bot-authored
    Telegram messages); ``TELEGRAM_AGENT_NAME`` and ``TELEGRAM_MSG_FORWARD``
    provide the relay sender and notice.
    """
    chat_id = _AUTH_STORE.chat_id_for_token(_bearer_token(request))
    if not _TELEGRAM_BOT_TOKEN and not _AGENT_MODE:
        raise HTTPException(
            status_code=503,
            detail="Telegram forwarding disabled: TELEGRAM_BOT_TOKEN not configured.",
        )
    if not chat_id:
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
