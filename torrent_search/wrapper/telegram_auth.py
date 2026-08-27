"""Telegram access auth: pairing challenges and the authorized-session store.

Flow: the Web UI asks the API for a one-time pairing code (challenge). The
user pastes it into their MCP agent together with their Telegram chat id;
the agent calls the register endpoint (gated by
``TORRENT_SEARCH_API_KEY``) or the ``authorize_webapp`` tool.
Once approved, the browser claims the challenge and receives a long-lived
random session token, kept in localStorage and sent as a Bearer header.
The server persists only SHA-256 hashes, mapped ``chat_id -> token``
(``authorized_tokens.json``). Logout deletes the mapping (revocation).
"""

import hashlib
import json
import logging
import os
import secrets
import tempfile
import time
from pathlib import Path

logger = logging.getLogger("Torrent Search")

SESSION_TTL_SECONDS = 365 * 24 * 3600  # "forever" within browser limits
DEFAULT_AUTH_FILE = "./authorized_tokens.json"
DEFAULT_CHALLENGE_TTL = 300.0  # 5 minutes to get the code approved
MAX_PENDING_CHALLENGES = 50


def hash_token(token: str) -> str:
    """SHA-256 of a session token; only hashes ever touch disk."""
    return hashlib.sha256(token.encode()).hexdigest()


class TelegramAuthStore:
    """Persistent ``chat_id -> token hash`` allow-list.

    The file is re-read whenever its mtime+size change, so a standalone MCP
    process and the REST API can share one ``authorized_tokens.json``.
    A missing file means "no sessions"; a corrupt file fails closed.
    """

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path or os.getenv("TELEGRAM_AUTH_FILE") or DEFAULT_AUTH_FILE)
        self._sessions: dict[str, dict[str, object]] = {}  # chat_id -> entry
        self._fingerprint: tuple[int, int] | None = None
        self._loaded = False

    def _reload_if_changed(self) -> None:
        try:
            stat = self.path.stat()
            fingerprint = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            if self._loaded:
                return  # file vanished between checks; keep in-memory state
            self._sessions, self._fingerprint, self._loaded = {}, None, True
            return
        if self._loaded and fingerprint == self._fingerprint:
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            sessions = data["sessions"] if isinstance(data, dict) else []
            self._sessions = {
                entry["chat_id"]: entry
                for entry in sessions
                if isinstance(entry, dict)
                and "chat_id" in entry
                and "token_hash" in entry
            }
            self._fingerprint = fingerprint
        except FileNotFoundError:
            self._sessions, self._fingerprint = {}, fingerprint
        except Exception:  # noqa: BLE001 - corrupt store must fail closed
            logger.warning("Invalid telegram auth file %s; ignoring.", self.path)
            if not self._loaded:
                self._sessions, self._fingerprint = {}, fingerprint
        self._loaded = True

    def save(self) -> None:
        """Atomically persist the session hashes with tight permissions."""
        payload = {
            "version": 1,
            "sessions": [
                {
                    "chat_id": chat_id,
                    "token_hash": entry["token_hash"],
                    "created": entry["created"],
                }
                for chat_id, entry in sorted(
                    self._sessions.items(), key=lambda item: str(item[0])
                )
            ],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=self.path.parent, prefix=".authorized-tokens-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
                handle.write("\n")
            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, self.path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        self._fingerprint = (self.path.stat().st_mtime_ns, self.path.stat().st_size)
        self._loaded = True

    def add_session(self, chat_id: str, token: str) -> None:
        """Map ``chat_id`` to a new session token (re-issuing replaces)."""
        self._reload_if_changed()
        self._sessions[str(chat_id)] = {
            "token_hash": hash_token(token),
            "created": int(time.time()),
        }
        self.save()

    def chat_id_for_token(self, token: str) -> str | None:
        self._reload_if_changed()
        token_hash = hash_token(token)
        for chat_id, entry in self._sessions.items():
            if entry["token_hash"] == token_hash:
                return str(chat_id)
        return None

    def remove_token(self, token: str) -> bool:
        """Revoke the session matching ``token``; True when one was removed."""
        self._reload_if_changed()
        token_hash = hash_token(token)
        for chat_id, entry in list(self._sessions.items()):
            if entry["token_hash"] == token_hash:
                del self._sessions[chat_id]
                self.save()
                return True
        return False

    def __len__(self) -> int:
        self._reload_if_changed()
        return len(self._sessions)


class ChallengeManager:
    """In-memory pairing codes: ``pending -> approved -> consumed``.

    Codes are single-use, TTL-bounded and capacity-capped. ``approve`` marks
    a pending code approved together with the registrant's chat id;
    ``consume`` exchanges an approved code for a session exactly once
    (browser side) and returns that chat id.
    """

    def __init__(
        self, ttl: float | None = None, max_pending: int = MAX_PENDING_CHALLENGES
    ) -> None:
        self.ttl = ttl if ttl is not None else DEFAULT_CHALLENGE_TTL
        self.max_pending = max_pending
        self._pending: dict[str, float] = {}  # code -> expires (monotonic)
        self._approved: dict[str, tuple[float, str]] = {}  # code -> (expires, chat_id)

    def _sweep(self) -> None:
        now = time.monotonic()
        for code, expires in [(c, e) for c, e in self._pending.items() if e <= now]:
            del self._pending[code]
            logger.info("Pairing challenge expired unused.")
        for code, (expires, _chat_id) in [
            (c, e) for c, e in self._approved.items() if e[0] <= now
        ]:
            del self._approved[code]
            logger.info("Approved pairing code expired unclaimed.")

    def consume(self, code: str) -> str | None:
        """Exchange an approved code exactly once; returns its chat id."""
        self._sweep()
        entry = self._approved.pop(code, None)
        if entry is None:
            return None
        expires, chat_id = entry
        if expires <= time.monotonic():
            return None
        return chat_id

    def create(self) -> tuple[str, float]:
        """Return a fresh ``(code, ttl_seconds)``."""
        self._sweep()
        while len(self._pending) >= self.max_pending:
            oldest = min(self._pending.items(), key=lambda item: item[1])[0]
            del self._pending[oldest]
            logger.info("Challenge capacity reached; evicted oldest pending code.")
        code = secrets.token_urlsafe(32)
        self._pending[code] = time.monotonic() + self.ttl
        return code, self.ttl

    def poll(self, code: str) -> str:
        """``"pending"`` or ``"approved"``; anything else reads as expired."""
        self._sweep()
        if code in self._approved:
            return "approved"
        return "pending" if code in self._pending else "expired"

    def approve(self, code: str, chat_id: str) -> bool:
        """Mark a pending code approved, bound to the registrant's chat id."""
        self._sweep()
        expires = self._pending.pop(code, None)
        if expires is None or expires <= time.monotonic():
            return False
        self._approved[code] = (expires, chat_id)
        return True

    def cancel(self, code: str) -> bool:
        return self._pending.pop(code, None) is not None

    def __len__(self) -> int:
        self._sweep()
        return len(self._pending)


class RateLimiter:
    """Tiny sliding-window limiter (per key), in-memory, no dependencies."""

    def __init__(self, max_events: int, per_seconds: float) -> None:
        self.max_events = max_events
        self.per_seconds = per_seconds
        self._events: dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        window = self._events.setdefault(key, [])
        cutoff = now - self.per_seconds
        while window and window[0] <= cutoff:
            window.pop(0)
        if len(window) >= self.max_events:
            return False
        window.append(now)
        return True


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


__all__: list[str] = [
    "SESSION_TTL_SECONDS",
    "ChallengeManager",
    "RateLimiter",
    "TelegramAuthStore",
    "hash_token",
    "new_session_token",
]
