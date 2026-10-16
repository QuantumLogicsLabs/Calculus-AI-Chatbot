"""Live-provider control flow tested with deterministic stubs, never Groq."""
import asyncio
import logging
import os
import sqlite3
import subprocess
import sys
import time
from types import SimpleNamespace

import httpx
import pytest
from starlette.testclient import TestClient

from aiService.services import llm_client as llm
from aiService.services.llm_client import ask_openai as real_json, ask_openai_stream as real_stream
from aiService.chatbot import app as ai_app
from backend.app.main import app as backend_app
from backend.app.routes import chat


class Provider:
    def __init__(self, result=None, error=None, delay=0):
        self.result, self.error, self.delay = result, error, delay
        self.calls = []
        self.chat = SimpleNamespace(completions=self)

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.result


def answer(text, finish="stop"):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason=finish)])


def chunk(text="", finish=None):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text), finish_reason=finish)])


class Stream:
    def __init__(self, events, delay=0):
        self.events, self.delay, self.closed = events, delay, False

    async def __aiter__(self):
        for event in self.events:
            if self.delay:
                await asyncio.sleep(self.delay)
            if isinstance(event, Exception):
                raise event
            yield event

    async def close(self):
        self.closed = True


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(llm, "USE_MOCK", False)
    monkeypatch.setattr(llm, "ask_openai", real_json)
    monkeypatch.setattr(llm, "ask_openai_stream", real_stream)
    monkeypatch.setattr(llm, "_primary_circuit", llm.CircuitBreaker(2, 60))
    return monkeypatch


@pytest.mark.asyncio
async def test_json_success_logs_source_and_caches(live, caplog):
    provider = Provider(answer("The derivative is 3*x**2"))
    live.setattr(llm, "client", provider)
    with caplog.at_level(logging.INFO):
        first = await llm.ask_llm("Find derivative of x**3")
        second = await llm.ask_llm("Find derivative of x**3")
    assert first == second == "The derivative is 3*x**2"
    assert len(provider.calls) == 1
    assert "served_by=primary mode=live" in caplog.text
    assert "served_by=cache mode=live" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [RuntimeError("secret-provider-body"), TimeoutError("secret-provider-body")])
async def test_json_failure_never_returns_mock_or_caches(live, caplog, error):
    live.setattr(llm, "client", Provider(error=error))
    with pytest.raises(llm.LLMUnavailable) as caught:
        await llm.ask_llm("Find derivative of x**3")
    assert "secret-provider-body" not in str(caught.value) + caplog.text
    assert not llm._response_cache
    assert llm._primary_circuit.failure_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("text,finish", [("", "stop"), ("Partial result", "length")])
async def test_empty_or_truncated_json_rejected(live, text, finish):
    live.setattr(llm, "client", Provider(answer(text, finish)))
    with pytest.raises(llm.LLMUnavailable):
        await llm.ask_llm("Explain limits")
    assert not llm._response_cache


@pytest.mark.asyncio
async def test_circuit_opens_and_single_probe_recovers(live):
    provider = Provider(error=RuntimeError("offline"))
    live.setattr(llm, "client", provider)
    for _ in range(3):
        with pytest.raises(llm.LLMUnavailable):
            await llm.ask_llm("Explain integrals")
    assert len(provider.calls) == 2
    circuit = llm._primary_circuit
    assert circuit.state == "open"
    circuit.opened_at = time.monotonic() - 61
    assert circuit.allow_request()
    assert not circuit.allow_request()  # Exactly one half-open probe.
    circuit.state = "open"
    provider.error, provider.result = None, answer("An integral accumulates change.")
    assert await llm.ask_llm("Explain integrals") == "An integral accumulates change."
    assert circuit.state == "closed" and circuit.failure_count == 0


@pytest.mark.asyncio
async def test_complete_stream_preserved_and_closed(live):
    stream = Stream([chunk("$$x^2"), chunk("$$"), chunk(finish="stop")])
    provider = Provider(stream)
    live.setattr(llm, "client", provider)
    result = "".join([part async for part in llm.ask_llm_stream("Integrate 2*x")])
    assert result == "$$x^2$$" and stream.closed
    assert "".join([part async for part in llm.ask_llm_stream("Integrate 2*x")]) == result
    assert len(provider.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("events", [
    [RuntimeError("secret-stream-body")],
    [chunk("Partial"), RuntimeError("secret-stream-body")],
    [chunk("Partial")],
    [chunk("Partial"), chunk(finish="length")],
    [chunk(finish="stop")],
])
async def test_failed_or_incomplete_stream_not_cached(live, events, caplog):
    stream = Stream(events)
    live.setattr(llm, "client", Provider(stream))
    with pytest.raises(llm.LLMUnavailable):
        _ = [part async for part in llm.ask_llm_stream("Explain partial derivatives")]
    assert stream.closed and not llm._response_cache
    assert "secret-stream-body" not in caplog.text


@pytest.mark.asyncio
async def test_stream_setup_and_idle_timeout(live):
    live.setattr(llm, "PRIMARY_TIMEOUT_SECONDS", 0.005)
    live.setattr(llm, "client", Provider(delay=0.05))
    with pytest.raises(llm.LLMUnavailable) as caught:
        _ = [part async for part in llm.ask_llm_stream("Explain gradients")]
    assert caught.value.code == "ai_timeout"
    stream = Stream([chunk("Hello"), chunk(finish="stop")], delay=0.05)
    live.setattr(llm, "client", Provider(stream))
    with pytest.raises(llm.LLMUnavailable) as caught:
        _ = [part async for part in llm.ask_llm_stream("Explain gradients")]
    assert caught.value.code == "ai_timeout" and stream.closed


@pytest.mark.asyncio
async def test_cancelled_stream_closes_provider_and_does_not_cache(live):
    stream = Stream([chunk("Partial"), chunk("More"), chunk(finish="stop")])
    live.setattr(llm, "client", Provider(stream))
    response = llm.ask_llm_stream("Explain derivatives")
    assert await anext(response) == "Partial"
    await response.aclose()
    assert stream.closed and not llm._response_cache


@pytest.mark.asyncio
async def test_total_stream_deadline_is_enforced(live):
    live.setattr(llm, "STREAM_TOTAL_TIMEOUT_SECONDS", 0.015)
    stream = Stream([chunk("First"), chunk("Second"), chunk(finish="stop")], delay=0.01)
    live.setattr(llm, "client", Provider(stream))
    with pytest.raises(llm.LLMUnavailable) as caught:
        _ = [part async for part in llm.ask_llm_stream("Explain derivatives")]
    assert caught.value.code == "ai_timeout" and stream.closed
    assert not llm._response_cache


def test_cache_context_isolation(monkeypatch):
    original = llm._cache_key("x", "calculus", "beginner", [], "summary A")
    assert original != llm._cache_key("X", "calculus", "beginner", [], "summary A")
    assert original != llm._cache_key("x", "calculus", "beginner", [], "summary B")
    monkeypatch.setattr(llm, "USE_MOCK", False)
    assert original != llm._cache_key("x", "calculus", "beginner", [], "summary A")


def test_ai_errors_are_sanitized_and_stream_never_finishes(live):
    live.setattr(llm, "client", Provider(error=RuntimeError("secret-key-and-provider-body")))
    with TestClient(ai_app) as client:
        result = client.post("/chat", json={"message": "Explain integrals"})
        assert result.status_code == 503 and result.json()["code"] == "ai_unavailable"
        stream = client.post("/chat/stream", json={"message": "Explain gradients"})
    assert '"error"' in stream.text and '"done"' not in stream.text
    assert "secret-key-and-provider-body" not in result.text + stream.text


@pytest.mark.parametrize("endpoint", ["/api/chat/", "/api/chat/stream"])
def test_backend_failures_never_persist_answers(live, isolated_db, endpoint):
    live.setattr(llm, "client", Provider(error=RuntimeError("secret-key")))
    real_client = httpx.AsyncClient
    live.setattr(chat.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.ASGITransport(app=ai_app), **kw))
    live.setattr(chat, "require_user", lambda request: 5)
    with TestClient(backend_app) as client:
        response = client.post(endpoint, json={"messages": [{"role": "user", "content": "Find the gradient"}]})
    if endpoint.endswith("stream"):
        assert '"error"' in response.text and '"done"' not in response.text
    else:
        assert response.status_code == 503
    with sqlite3.connect(isolated_db) as db:
        assert db.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0] == 0
    assert not llm._response_cache
    assert "secret-key" not in response.text


@pytest.mark.parametrize("mode,extra,passes", [
    (None, {}, False), ("False", {}, False), ("True", {}, True),
    ("typo", {}, False), ("True", {"PRIMARY_TIMEOUT_SECONDS": "nan"}, False),
])
def test_startup_requires_explicit_demo_or_credentials(mode, extra, passes):
    env = dict(os.environ, GROQ_API_KEY="", PYTHONUTF8="1", **extra)
    env.pop("USE_MOCK", None)
    if mode is not None:
        env["USE_MOCK"] = mode
    result = subprocess.run([
        sys.executable, "-B", "-c",
        "import dotenv; dotenv.load_dotenv=lambda *a,**k: None; import aiService.services.llm_client",
    ], env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert (result.returncode == 0) is passes, result.stderr


@pytest.mark.parametrize("payload", [
    'data: {"delta":"Partial"}\n\n',
    'data: {"delta":"Partial"}\n\ndata: {"error":"secret-upstream-body"}\n\n',
    'data: invalid-json\n\n',
    'data: {"done":true}\n\n',
])
def test_backend_rejects_bad_upstream_streams(monkeypatch, isolated_db, payload):
    from starlette.applications import Starlette
    from starlette.responses import StreamingResponse
    from starlette.routing import Route

    async def endpoint(request):
        async def events():
            yield payload
        return StreamingResponse(events(), media_type="text/event-stream")

    upstream = Starlette(routes=[Route("/chat/stream", endpoint, methods=["POST"])])
    real_client = httpx.AsyncClient
    monkeypatch.setattr(chat.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.ASGITransport(app=upstream), **kw))
    monkeypatch.setattr(chat, "require_user", lambda request: 5)
    with TestClient(backend_app) as client:
        response = client.post("/api/chat/stream", json={"messages": [{"role": "user", "content": "Explain limits"}]})
    assert '"error"' in response.text and '"done"' not in response.text
    assert "secret-upstream-body" not in response.text
    with sqlite3.connect(isolated_db) as db:
        assert db.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0] == 0
