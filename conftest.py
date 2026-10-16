"""Offline pytest defaults; real-provider evaluations run as explicit modules."""
import os
import sqlite3

import pytest

# Do this before test collection imports the AI client, even if a local .env
# contains real credentials. pytest must never spend API credits.
os.environ["USE_MOCK"] = "True"
os.environ["GROQ_API_KEY"] = ""


@pytest.fixture(autouse=True)
def offline_llm(monkeypatch):
    from aiService.services import llm_client

    async def reject_provider(*args, **kwargs):
        pytest.fail("Offline test attempted a real-provider path")

    async def reject_provider_stream(*args, **kwargs):
        pytest.fail("Offline test attempted a real-provider stream")
        yield ""  # Keep the same async-generator protocol as the provider.

    monkeypatch.setattr(llm_client, "USE_MOCK", True)
    monkeypatch.setattr(llm_client, "ask_openai", reject_provider)
    monkeypatch.setattr(llm_client, "ask_openai_stream", reject_provider_stream)
    monkeypatch.setattr(llm_client, "client", None)
    llm_client._response_cache.clear()
    yield
    llm_client._response_cache.clear()


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    from backend.app.database import db
    from backend.app.routes import chat

    path = tmp_path / "chat-test.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(db.SCHEMA)
    monkeypatch.setattr(db, "DB_PATH", str(path))
    monkeypatch.setattr(db, "_initialized", True)
    monkeypatch.setattr(chat, "_rate_limiter", chat.RateLimiter())
    return path
