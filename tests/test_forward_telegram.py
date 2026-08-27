"""Tests for POST /forward_telegram (server-side bot relay)."""

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from torrent_search import api_server
from torrent_search.wrapper import telegram_auth as ta

MAGNET = "magnet:?xt=urn:btih:" + "ab" * 20 + "&dn=Show%20S01E01&tr=udp%3A%2F%2Ft1"
FILENAME = "Show S01E01 1080p"


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield TestClient(api_server.app)


class _FakeBotResponse:
    def __init__(self, payload: dict[str, Any], fail: bool = False) -> None:
        self._payload = payload
        self._fail = fail

    def raise_for_status(self) -> None:
        if self._fail:
            raise RuntimeError("boom")

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeBotClient:
    def __init__(self, *, ok: bool = True, data_ok: bool = True) -> None:
        self.sent: list[dict[str, Any]] = []
        self._ok = ok
        self._data_ok = data_ok

    async def post(self, path: str, json: Any = None) -> _FakeBotResponse:
        self.sent.append({"path": path, **json})
        return _FakeBotResponse(
            {"ok": self._data_ok, "description": "Bad Request: x"}, fail=not self._ok
        )


@pytest.fixture
def paired(monkeypatch: Any, tmp_path: Any) -> str:
    """Bot token configured + a valid session token for chat 12345."""
    store = ta.TelegramAuthStore(tmp_path / "tokens.json")
    store.add_session("12345", "sess-token")
    monkeypatch.setattr(api_server, "_AUTH_STORE", store)
    monkeypatch.setattr(api_server, "_TELEGRAM_BOT_TOKEN", "bot-token")
    return "sess-token"


def test_forward_disabled_without_bot_token(client: TestClient) -> None:
    response = client.post(
        "/forward_telegram", json={"filename": FILENAME, "magnet_link": MAGNET}
    )
    assert response.status_code == 503
    assert "TELEGRAM_BOT_TOKEN" in response.json()["detail"]


def test_bot_client_is_configured() -> None:
    """The shared Telegram API client targets the Bot API base."""
    bot = api_server._bot()
    assert str(bot.base_url).rstrip("/") == "https://api.telegram.org"


def test_forward_requires_valid_session(paired: str, client: TestClient) -> None:
    assert (
        client.post(
            "/forward_telegram", json={"filename": FILENAME, "magnet_link": MAGNET}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/forward_telegram",
            json={"filename": FILENAME, "magnet_link": MAGNET},
            headers={"Authorization": "Bearer wrong"},
        ).status_code
        == 401
    )


def test_forward_sends_pruned_magnet_when_enabled(
    paired: str, client: TestClient, monkeypatch: Any
) -> None:
    monkeypatch.setattr(api_server, "_PRUNE_MAGNET_LINKS", True)
    fake_bot = _FakeBotClient()
    monkeypatch.setattr(api_server, "_bot", lambda: fake_bot)
    response = client.post(
        "/forward_telegram",
        json={
            "filename": FILENAME,
            "magnet_link": MAGNET,
            "size": "1.2 GiB",
            "seeders": 10,
        },
        headers={"Authorization": f"Bearer {paired}"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "sent"}
    message = fake_bot.sent[0]
    assert message["chat_id"] == "12345"
    # Pruned: trackers stripped, dn re-encoded from the display filename.
    assert message["text"].endswith(
        "magnet:?xt=urn:btih:" + "ab" * 20 + "&dn=" + FILENAME.replace(" ", "%20")
    )
    assert "Size: 1.2 GiB" in message["text"]


def test_forward_keeps_full_magnet_when_prune_disabled(
    paired: str, client: TestClient, monkeypatch: Any
) -> None:
    fake_bot = _FakeBotClient()
    monkeypatch.setattr(api_server, "_bot", lambda: fake_bot)
    response = client.post(
        "/forward_telegram",
        json={"filename": FILENAME, "magnet_link": MAGNET},
        headers={"Authorization": f"Bearer {paired}"},
    )
    assert response.status_code == 200
    assert fake_bot.sent[0]["text"].endswith(MAGNET)


def test_forward_maps_bot_failures_to_502(
    paired: str, client: TestClient, monkeypatch: Any
) -> None:
    http_error = _FakeBotClient(ok=False)  # raise_for_status raises
    monkeypatch.setattr(api_server, "_bot", lambda: http_error)
    headers = {"Authorization": f"Bearer {paired}"}
    payload = {"filename": FILENAME, "magnet_link": MAGNET}
    assert (
        client.post("/forward_telegram", json=payload, headers=headers).status_code
        == 502
    )
    api_error = _FakeBotClient(data_ok=False)  # telegram answers ok:false
    monkeypatch.setattr(api_server, "_bot", lambda: api_error)
    assert (
        client.post("/forward_telegram", json=payload, headers=headers).status_code
        == 502
    )


def test_forward_rate_limited_per_chat(
    paired: str, client: TestClient, monkeypatch: Any
) -> None:
    import time

    monkeypatch.setattr(api_server, "_bot", lambda: _FakeBotClient())
    api_server._FORWARD_LIMITER._events["12345"] = [
        time.monotonic()
    ] * api_server._FORWARD_LIMITER.max_events
    response = client.post(
        "/forward_telegram",
        json={"filename": FILENAME, "magnet_link": MAGNET},
        headers={"Authorization": f"Bearer {paired}"},
    )
    assert response.status_code == 429


class _FakeRelayClient:
    def __init__(self, *, ok: bool = True) -> None:
        self.sent: list[dict[str, Any]] = []
        self._ok = ok

    async def post(
        self, url: str, json: Any = None, headers: Any = None
    ) -> _FakeBotResponse:
        self.sent.append({"url": url, "json": json, "headers": headers})
        return _FakeBotResponse({}, fail=not self._ok)


def test_agent_mode_posts_to_agent_relay(
    paired: str, client: TestClient, monkeypatch: Any
) -> None:
    """Relay URL + token set => payload POSTed to the agent's HTTP relay."""
    monkeypatch.setattr(api_server, "_TELEGRAM_AGENT_NAME", "My Agent")
    monkeypatch.setattr(api_server, "_TELEGRAM_MSG_FORWARD", "Torrent received!")
    monkeypatch.setattr(api_server, "_AGENT_RELAY_URL", "http://agent:4041/relay")
    monkeypatch.setattr(api_server, "_AGENT_RELAY_TOKEN", "relay-secret")
    monkeypatch.setattr(api_server, "_AGENT_MODE", True)
    fake_relay = _FakeRelayClient()
    monkeypatch.setattr(api_server, "_relay", lambda: fake_relay)
    api_server._FORWARD_LIMITER._events.pop(
        "12345", None
    )  # shared limiter across tests
    response = client.post(
        "/forward_telegram",
        json={"filename": FILENAME, "magnet_link": MAGNET, "size": "1.2 GiB"},
        headers={"Authorization": f"Bearer {paired}"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "sent"}
    call = fake_relay.sent[0]
    assert call["url"] == "http://agent:4041/relay"
    assert call["json"]["chat_id"] == "12345"
    assert call["json"]["sender"] == "My Agent"
    assert call["json"]["notice"] == "Torrent received!"
    assert call["json"]["prompt"] == f"Download this torrent: {MAGNET}"
    assert call["headers"]["X-Relay-Token"] == "relay-secret"


def test_agent_mode_relay_failure_maps_to_502(
    paired: str, client: TestClient, monkeypatch: Any
) -> None:
    monkeypatch.setattr(api_server, "_AGENT_RELAY_URL", "http://agent:4041/relay")
    monkeypatch.setattr(api_server, "_AGENT_RELAY_TOKEN", "relay-secret")
    monkeypatch.setattr(api_server, "_AGENT_MODE", True)
    monkeypatch.setattr(api_server, "_relay", lambda: _FakeRelayClient(ok=False))
    api_server._FORWARD_LIMITER._events.pop("12345", None)
    response = client.post(
        "/forward_telegram",
        json={"filename": FILENAME, "magnet_link": MAGNET},
        headers={"Authorization": f"Bearer {paired}"},
    )
    assert response.status_code == 502


def test_relay_client_is_configured() -> None:
    """The shared relay client has no Bot API base (absolute URLs)."""
    relay = api_server._relay()
    assert relay.base_url == httpx.URL()
