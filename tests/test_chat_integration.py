"""Backend -> AI ASGI integration in mock mode, with no running servers."""
import json

import httpx
import pytest
from starlette.testclient import TestClient

from backend.app.main import app
from backend.app.routes import chat
from aiService.chatbot import app as ai_app


@pytest.fixture
def client(isolated_db, monkeypatch):
    real_client = httpx.AsyncClient

    def ai_transport_client(**kwargs):
        return real_client(transport=httpx.ASGITransport(app=ai_app), **kwargs)

    monkeypatch.setattr(chat.httpx, "AsyncClient", ai_transport_client)
    with TestClient(app) as test_client:
        yield test_client


def frames(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


def test_guest_json_and_stream_flow(client):
    history = [{"role": "user", "content": "Explain derivatives"},
               {"role": "assistant", "content": "They describe rates of change."}]
    payload = {"messages": history + [{"role": "user", "content": "Give another example"}],
               "context": "Partial derivatives", "topic_key": "partials"}
    response = client.post("/api/chat/", json=payload)
    assert response.status_code == 200
    assert "Give another example" in response.json()["reply"]
    assert "2 messages" in response.json()["reply"]
    assert response.json()["message_id"] is None
    # Use another question to exercise the stream provider path, not JSON cache replay.
    payload["messages"][-1]["content"] = "Explain the gradient"
    response = client.post("/api/chat/stream", json=payload)
    assert response.status_code == 200
    events = frames(response)
    text = "".join(event.get("delta", "") for event in events)
    assert "Explain the gradient" in text
    assert "History length: 2" in text
    assert events[-1]["done"] is True
    assert not any(event.get("error") for event in events)


def test_authenticated_stream_history_and_export(client, monkeypatch):
    # Bypass only identity lookup, not persistence or route handlers.
    monkeypatch.setattr(chat, "require_user", lambda request: 7)
    session = client.post("/api/chat/sessions", json={"title": "Integration"}).json()["data"]["session_id"]
    response = client.post("/api/chat/stream", json={
        "messages": [{"role": "user", "content": "Find the derivative of x**3"}],
        "context": "Derivatives", "topic_key": "derivatives",
    })
    done = frames(response)[-1]
    assert done["done"] and done["session_id"] == session and done["message_id"]
    history = client.get(f"/api/chat/history/{session}").json()["data"]["messages"]
    assert [item["message_type"] for item in history] == ["user", "assistant"]
    assert history[-1]["id"] == done["message_id"]
    exported = client.get(f"/api/chat/sessions/{session}/export")
    assert exported.status_code == 200
    assert "Find the derivative of x**3" in exported.text


@pytest.mark.parametrize("endpoint", ["/api/chat/", "/api/chat/stream"])
def test_invalid_chat_body_rejected(client, endpoint):
    assert client.post(endpoint, json={}).status_code == 400
    assert client.post(endpoint, content="not-json").status_code == 400


@pytest.mark.parametrize("endpoint", ["/api/chat/", "/api/chat/stream"])
def test_guest_rate_limit_is_enforced(client, endpoint):
    payload = {"messages": [{"role": "user", "content": "Explain derivatives"}]}
    for _ in range(10):
        assert client.post("/api/chat/", json=payload).status_code == 200
    response = client.post(endpoint, json=payload)
    assert response.status_code == 429
    assert response.json()["retry_after"] > 0
