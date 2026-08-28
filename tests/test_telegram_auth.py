"""Telegram access auth: store, challenges, and the REST pairing flow."""

import json
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from torrent_search import api_server
from torrent_search.wrapper import telegram_auth as ta


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield TestClient(api_server.app)


@pytest.fixture
def auth_env(monkeypatch: Any, tmp_path: Any) -> Any:
    """Isolated auth state: temp token file, handle + secret configured."""
    store = ta.TelegramAuthStore(tmp_path / "authorized_tokens.json")
    monkeypatch.setattr(api_server, "_AUTH_STORE", store)
    monkeypatch.setattr(api_server, "_CHALLENGES", ta.ChallengeManager(ttl=900))
    monkeypatch.setattr(api_server, "_REGISTER_SECRET", "reg-secret-123")
    monkeypatch.setattr(api_server, "_TELEGRAM_BOT_HANDLE", "mybot")
    return store


# ---- Store unit tests -------------------------------------------------------


def test_store_roundtrip_and_hash_only(tmp_path: Any) -> None:
    path = tmp_path / "authorized_tokens.json"
    store = ta.TelegramAuthStore(path)
    store.add_session("12345", "token-a")
    assert store.chat_id_for_token("token-a") == "12345"
    assert store.chat_id_for_token("token-b") is None
    raw = path.read_text()
    assert "token-a" not in raw  # only hashes are persisted
    assert ta.hash_token("token-a") in raw
    assert "12345" in raw  # chat ids are stored in the clear


def test_store_multiple_sessions_per_chat(tmp_path: Any) -> None:
    store = ta.TelegramAuthStore(tmp_path / "authorized_tokens.json")
    store.add_session("12345", "token-a")
    store.add_session("12345", "token-b")  # second browser, same chat id
    assert store.chat_id_for_token("token-a") == "12345"
    assert store.chat_id_for_token("token-b") == "12345"
    assert store.remove_token("token-a")  # revoking one browser...
    assert store.chat_id_for_token("token-a") is None
    assert store.chat_id_for_token("token-b") == "12345"  # ...keeps the other


def test_store_creates_missing_file(tmp_path: Any) -> None:
    path = tmp_path / "authorized_tokens.json"
    assert not path.exists()
    ta.TelegramAuthStore(path)
    assert path.exists()
    assert ta.TelegramAuthStore(path).chat_id_for_token("anything") is None


def test_store_init_fails_closed_when_unwritable(tmp_path: Any) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("")  # a file, not a directory
    store = ta.TelegramAuthStore(blocker / "tokens.json")
    assert store.chat_id_for_token("anything") is None


def test_store_purges_expired_sessions_at_startup(tmp_path: Any) -> None:
    path = tmp_path / "authorized_tokens.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "sessions": [
                    {
                        "chat_id": "1",
                        "token_hash": ta.hash_token("old"),
                        "created": 0,
                    },
                    {
                        "chat_id": "2",
                        "token_hash": ta.hash_token("fresh"),
                        "created": int(time.time()),
                    },
                ],
            }
        )
    )
    store = ta.TelegramAuthStore(path)
    assert store.chat_id_for_token("old") is None  # purged at startup
    assert store.chat_id_for_token("fresh") == "2"


def test_store_remove_token_revokes(tmp_path: Any) -> None:
    store = ta.TelegramAuthStore(tmp_path / "authorized_tokens.json")
    store.add_session("12345", "token-a")
    assert store.remove_token("token-a")
    assert store.chat_id_for_token("token-a") is None
    assert not store.remove_token("token-a")  # already gone


def test_store_corrupt_file_fails_closed(tmp_path: Any) -> None:
    path = tmp_path / "authorized_tokens.json"
    path.write_text("{not json")
    store = ta.TelegramAuthStore(path)
    assert store.chat_id_for_token("anything") is None
    store.add_session("1", "fresh")  # recovers by rewriting a valid file
    assert store.chat_id_for_token("fresh") == "1"


def test_store_reloads_when_file_changes(tmp_path: Any) -> None:
    path = tmp_path / "authorized_tokens.json"
    first = ta.TelegramAuthStore(path)
    first.add_session("1", "token-a")
    second = ta.TelegramAuthStore(path)  # separate process view
    assert second.chat_id_for_token("token-a") == "1"
    second.add_session("2", "token-b")
    assert first.chat_id_for_token("token-b") == "2"  # mtime-triggered reload


# ---- Challenge unit tests ----------------------------------------------------


def test_challenge_lifecycle_binds_chat_id() -> None:
    challenges = ta.ChallengeManager(ttl=900)
    code, ttl = challenges.create()
    assert ttl == 900
    assert challenges.poll(code) == "pending"
    assert challenges.approve(code, "12345")
    assert challenges.poll(code) == "approved"
    assert challenges.consume(code) == "12345"
    assert challenges.poll(code) == "expired"  # single use
    assert challenges.consume(code) is None


def test_challenge_unknown_and_cancel() -> None:
    challenges = ta.ChallengeManager(ttl=900)
    assert challenges.poll("nope") == "expired"
    assert not challenges.approve("nope", "1")
    code, _ = challenges.create()
    assert challenges.cancel(code)
    assert challenges.poll(code) == "expired"


def test_challenge_ttl_expiry(monkeypatch: Any) -> None:
    challenges = ta.ChallengeManager(ttl=50)
    code, _ = challenges.create()
    real_monotonic = ta.time.monotonic
    monkeypatch.setattr(ta.time, "monotonic", lambda: real_monotonic() + 100)
    assert challenges.poll(code) == "expired"
    assert not challenges.approve(code, "1")


def test_challenge_capacity_eviction() -> None:
    challenges = ta.ChallengeManager(ttl=900, max_pending=2)
    challenges.create()
    challenges.create()
    code3, _ = challenges.create()  # evicts the oldest pending
    assert len(challenges) == 2
    assert challenges.poll(code3) == "pending"


def test_rate_limiter_window() -> None:
    limiter = ta.RateLimiter(max_events=2, per_seconds=60)
    assert limiter.allow("ip")
    assert limiter.allow("ip")
    assert not limiter.allow("ip")
    assert limiter.allow("other-ip")


def test_rate_limiter_drops_expired_events(monkeypatch: Any) -> None:
    ticks = iter([100.0, 111.0])
    monkeypatch.setattr(ta.time, "monotonic", lambda: next(ticks))
    limiter = ta.RateLimiter(max_events=2, per_seconds=10)
    assert limiter.allow("ip")
    assert limiter.allow("ip")
    # The t=100 event fell out of the sliding window before t=111 was appended.
    assert limiter._events["ip"] == [111.0]


# ---- REST pairing flow -------------------------------------------------------


def test_session_states(client: TestClient, auth_env: Any) -> None:
    unauth = client.get("/telegram/session").json()
    # The handle is public (pairing deep links need it); tokens are the gate.
    assert unauth == {
        "enabled": True,
        "authenticated": False,
        "handle": "mybot",
        "prune_magnet_links": False,
        "agent_name": None,
    }
    # A bogus token is rejected.
    bogus = client.get(
        "/telegram/session", headers={"Authorization": "Bearer nope"}
    ).json()
    assert bogus["authenticated"] is False


def test_full_pairing_flow(client: TestClient, auth_env: Any) -> None:
    challenge = client.post("/telegram/auth/challenge").json()
    code = challenge["code"]
    # Missing chat id is 422; a wrong registrar secret is 401.
    assert (
        client.post("/telegram/auth/register", params={"code": code}).status_code == 422
    )
    bad = client.post(
        "/telegram/auth/register",
        params={"code": code, "chat_id": "12345"},
        headers={"Authorization": "Bearer wrong"},
    )
    assert bad.status_code == 401
    ok = client.post(
        "/telegram/auth/register",
        params={"code": code, "chat_id": "12345"},
        headers={"Authorization": "Bearer reg-secret-123"},
    )
    assert ok.status_code == 200

    # Poll delivers the one-time session token bound to the chat id.
    approved = client.get("/telegram/auth/poll", params={"code": code}).json()
    assert approved["status"] == "approved"
    token = approved["token"]
    assert token
    replay = client.get("/telegram/auth/poll", params={"code": code}).json()
    assert replay == {"status": "expired"}  # single use

    # The token authenticates and reveals the handle.
    session = client.get(
        "/telegram/session", headers={"Authorization": f"Bearer {token}"}
    ).json()
    assert session == {
        "enabled": True,
        "authenticated": True,
        "handle": "mybot",
        "prune_magnet_links": False,
        "agent_name": None,
    }

    # Logout revokes the token server-side.
    assert (
        client.post(
            "/telegram/auth/logout", headers={"Authorization": f"Bearer {token}"}
        ).status_code
        == 200
    )
    assert auth_env.chat_id_for_token(token) is None
    after = client.get(
        "/telegram/session", headers={"Authorization": f"Bearer {token}"}
    ).json()
    assert after["authenticated"] is False


def test_pairing_survives_via_persisted_store(
    client: TestClient, auth_env: Any
) -> None:
    challenge = client.post("/telegram/auth/challenge").json()
    client.post(
        "/telegram/auth/register",
        params={"code": challenge["code"], "chat_id": "42"},
        headers={"Authorization": "Bearer reg-secret-123"},
    )
    token = client.get(
        "/telegram/auth/poll", params={"code": challenge["code"]}
    ).json()["token"]
    # A fresh store over the same file (simulated restart) still knows us.
    assert ta.TelegramAuthStore(auth_env.path).chat_id_for_token(token) == "42"


def test_cancel_drops_pending_challenge(client: TestClient, auth_env: Any) -> None:
    challenge = client.post("/telegram/auth/challenge").json()
    cancelled = client.delete(f"/telegram/auth/challenge/{challenge['code']}")
    assert cancelled.json() == {"status": "cancelled"}
    poll = client.get("/telegram/auth/poll", params={"code": challenge["code"]})
    assert poll.json() == {"status": "expired"}


def test_register_unknown_code(client: TestClient, auth_env: Any) -> None:
    response = client.post(
        "/telegram/auth/register",
        params={"code": "does-not-exist", "chat_id": "1"},
        headers={"Authorization": "Bearer reg-secret-123"},
    )
    assert response.status_code == 404


def test_disabled_without_bot_handle(monkeypatch: Any) -> None:
    monkeypatch.setattr(api_server, "_TELEGRAM_BOT_HANDLE", None)
    client = TestClient(api_server.app)
    assert client.post("/telegram/auth/challenge").status_code == 404
    # Integration off = no gate: the session reports ready.
    assert client.get("/telegram/session").json() == {
        "enabled": False,
        "authenticated": True,
        "handle": None,
        "prune_magnet_links": False,
        "agent_name": None,
    }


def test_register_disabled_without_secret(monkeypatch: Any, auth_env: Any) -> None:
    monkeypatch.setattr(api_server, "_REGISTER_SECRET", None)
    client = TestClient(api_server.app)
    assert (
        client.post(
            "/telegram/auth/register", params={"code": "x", "chat_id": "1"}
        ).status_code
        == 403
    )


def test_challenge_disabled_without_secret(monkeypatch: Any, auth_env: Any) -> None:
    monkeypatch.setattr(api_server, "_REGISTER_SECRET", None)
    client = TestClient(api_server.app)
    assert client.post("/telegram/auth/challenge").status_code == 404


def test_challenge_rate_limited(
    client: TestClient, auth_env: Any, monkeypatch: Any
) -> None:
    monkeypatch.setattr(
        api_server,
        "_CHALLENGE_LIMITER",
        ta.RateLimiter(max_events=2, per_seconds=60),
    )
    assert client.post("/telegram/auth/challenge").status_code == 200
    assert client.post("/telegram/auth/challenge").status_code == 200
    assert client.post("/telegram/auth/challenge").status_code == 429


def test_poll_rate_limited(client: TestClient, auth_env: Any, monkeypatch: Any) -> None:
    monkeypatch.setattr(
        api_server, "_POLL_LIMITER", ta.RateLimiter(max_events=1, per_seconds=60)
    )
    code = client.post("/telegram/auth/challenge").json()["code"]
    assert client.get("/telegram/auth/poll", params={"code": code}).status_code == 200
    assert client.get("/telegram/auth/poll", params={"code": code}).status_code == 429


def test_register_rate_limited(
    client: TestClient, auth_env: Any, monkeypatch: Any
) -> None:
    monkeypatch.setattr(
        api_server,
        "_REGISTER_LIMITER",
        ta.RateLimiter(max_events=1, per_seconds=60),
    )
    headers = {"Authorization": "Bearer reg-secret-123"}
    first = client.post(
        "/telegram/auth/register",
        params={"code": "x1", "chat_id": "1"},
        headers=headers,
    )
    assert first.status_code == 404  # unknown code, but the limiter counted it
    second = client.post(
        "/telegram/auth/register",
        params={"code": "x2", "chat_id": "1"},
        headers=headers,
    )
    assert second.status_code == 429


def test_store_keeps_memory_when_file_vanishes(tmp_path: Any) -> None:
    """Once loaded, a vanished file keeps the in-memory sessions (OSError branch)."""
    path = tmp_path / "tokens.json"
    store = ta.TelegramAuthStore(path)
    store.add_session("42", "tok")
    store.save()
    path.unlink()
    assert len(store) == 1


def test_save_cleans_tmp_on_failure(tmp_path: Any, monkeypatch: Any) -> None:
    """A failed atomic replace unlinks the temp file and re-raises."""
    store = ta.TelegramAuthStore(tmp_path / "tokens.json")
    store.add_session("42", "tok")

    def boom(*args: Any, **kwargs: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(ta.os, "replace", boom)
    with pytest.raises(OSError, match="disk full"):
        store.save()
    assert not list(tmp_path.glob(".authorized-tokens-*"))


def test_save_cleanup_survives_failing_unlink(tmp_path: Any, monkeypatch: Any) -> None:
    """Cleanup tolerates a failing temp unlink and still re-raises the write error."""
    store = ta.TelegramAuthStore(tmp_path / "tokens.json")

    def boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("disk full")

    def unlink_boom(*args: Any, **kwargs: Any) -> None:
        raise OSError("busy")

    monkeypatch.setattr(ta.json, "dump", boom)
    monkeypatch.setattr(ta.os, "unlink", unlink_boom)
    with pytest.raises(RuntimeError, match="disk full"):
        store.add_session("7", "tok")


def test_store_missing_file_fails_closed(tmp_path: Any) -> None:
    """A missing file reads as an empty allow-list (FileNotFoundError branch)."""
    store = ta.TelegramAuthStore(tmp_path / "nope.json")
    store._reload_if_changed()
    assert store._sessions == {} and store._loaded


def test_store_file_vanishes_between_stat_and_read(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """A file vanishing between stat and read reads as an empty allow-list."""
    store = ta.TelegramAuthStore(tmp_path / "tokens.json")
    store.add_session("42", "tok")
    store._fingerprint = (0, 0)  # force the changed-file path on next access

    def raise_missing(*args: Any, **kwargs: Any) -> str:
        raise FileNotFoundError

    monkeypatch.setattr(type(store.path), "read_text", raise_missing)
    assert len(store) == 0
    assert store.chat_id_for_token("tok") is None


def test_consume_expired_code_returns_none(monkeypatch: Any) -> None:
    """An approved-but-expired code exchanges to nothing."""
    challenges = ta.ChallengeManager(ttl=50)
    code, _ = challenges.create()
    assert challenges.approve(code, "42")
    real_monotonic = ta.time.monotonic
    monkeypatch.setattr(ta.time, "monotonic", lambda: real_monotonic() + 100)
    assert challenges.consume(code) is None


def test_consume_catches_expiry_between_sweep_and_check(monkeypatch: Any) -> None:
    """An approval expiring right after the sweep still consumes to nothing."""
    challenges = ta.ChallengeManager(ttl=50)
    code, _ = challenges.create()
    assert challenges.approve(code, "42")
    ticks = iter([0.0, float("inf")])
    monkeypatch.setattr(ta.time, "monotonic", lambda: next(ticks))
    assert challenges.consume(code) is None


def test_approved_code_sweeps_when_unclaimed(monkeypatch: Any) -> None:
    challenges = ta.ChallengeManager(ttl=50)
    code, _ = challenges.create()
    assert challenges.approve(code, "1")
    real_monotonic = ta.time.monotonic
    monkeypatch.setattr(ta.time, "monotonic", lambda: real_monotonic() + 100)
    assert challenges.poll(code) == "expired"


def test_webui_html_never_contains_handle(client: TestClient, auth_env: Any) -> None:
    html = client.get("/").text
    assert "mybot" not in html
    assert "__STARS_" not in html  # starfield shadows are injected
