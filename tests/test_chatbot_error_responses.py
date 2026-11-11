"""Tests for structured JSON error responses in aiService endpoints."""
import pytest
from starlette.testclient import TestClient

from aiService.chatbot import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize("endpoint", ["/chat", "/chat/stream", "/summarize"])
def test_non_json_body_returns_structured_invalid_json_code(client, endpoint):
    """Endpoints must surface parse errors with structured code 'invalid_json'."""
    response = client.post(endpoint, content="not-a-valid-json-string", headers={"Content-Type": "application/json"})
    assert response.status_code == 400
    data = response.json()
    assert data["code"] == "invalid_json"
    assert "Invalid JSON body" in data["detail"]


@pytest.mark.parametrize("endpoint", ["/chat", "/chat/stream"])
def test_invalid_chat_body_returns_structured_invalid_request_code(client, endpoint):
    """Chat endpoints must return code 'invalid_request' when message or history is invalid."""
    response = client.post(endpoint, json={"message": "", "history": []})
    assert response.status_code == 400
    data = response.json()
    assert data["code"] == "invalid_request"
    assert "required" in data["detail"]


def test_invalid_summarize_body_returns_structured_invalid_request_code(client):
    """Summarize endpoint must return code 'invalid_request' when messages is not a list."""
    response = client.post("/summarize", json={"messages": "not-a-list"})
    assert response.status_code == 400
    data = response.json()
    assert data["code"] == "invalid_request"
    assert "messages must be an array" in data["detail"]
