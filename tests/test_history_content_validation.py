import pytest
from starlette.testclient import TestClient
from aiService.chatbot import _valid_chat_body, app

VALID_HISTORY = [
    {"role": "user", "content": "What is a derivative?"},
    {"role": "assistant", "content": "It measures the rate of change."},
]


@pytest.mark.parametrize("history,expected", [
    ([], True),
    (VALID_HISTORY, True),
    ([{"role": "user", "content": "Hello"}], True),
    ([{"role": "user", "content": ""}], False),
    ([{"role": "assistant", "content": ""}], False),
    ([{"role": "user", "content": "   "}], False),
    (
        [
            {"role": "user", "content": "What is a gradient?"},
            {"role": "assistant", "content": ""},
        ],
        False,
    ),
])
def test_valid_chat_body_rejects_empty_history_content(history, expected):
    """_valid_chat_body must reject any history item whose content is empty
    or whitespace-only, to prevent blank turns reaching the LLM."""
    body = {"message": "Follow-up", "history": history}
    assert _valid_chat_body(body) is expected


def test_empty_history_item_returns_400():
    """The /chat endpoint must return 400 when history has an empty-content turn."""
    with TestClient(app) as client:
        response = client.post("/chat", json={
            "message": "Explain limits",
            "history": [{"role": "user", "content": ""}],
        })
    assert response.status_code == 400


def test_whitespace_history_item_returns_400():
    """The /chat endpoint must return 400 when history has a whitespace-only turn."""
    with TestClient(app) as client:
        response = client.post("/chat", json={
            "message": "Explain limits",
            "history": [{"role": "assistant", "content": "   "}],
        })
    assert response.status_code == 400