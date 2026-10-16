"""Offline checks for conversation context reaching the model prompt.

These exercise the real AI HTTP route and prompt builder with a recording stub
at the model boundary; they do not claim a model understands the conversation.
"""
import pytest
from starlette.testclient import TestClient

from aiService import chatbot
from aiService.services.llm_client import _build_messages


@pytest.mark.parametrize("question,answer,followup", [
    ("What is the derivative of x^2?", "It is 2*x.", "Can you give another example?"),
    ("Explain the gradient.", "It gives the steepest increase.", "What does that direction mean?"),
    ("Find the integral of 2*x.", "It is x**2 + C.", "Now find the derivative of that."),
    ("What is a vector?", "It has magnitude and direction.", "Give me a practical example."),
])
def test_followup_preserves_history(monkeypatch, question, answer, followup):
    captured = []

    async def record_prompt(**kwargs):
        captured.extend(_build_messages(**kwargs))
        return "Recorded response"

    monkeypatch.setattr(chatbot, "ask_llm", record_prompt)
    history = [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]
    with TestClient(chatbot.app) as client:
        response = client.post("/chat", json={
            "message": followup, "topic": "Partial derivatives", "history": history,
            "summary": "Earlier calculus discussion", "difficulty": "beginner",
        })
    assert response.status_code == 200
    assert captured[-3:] == history + [{"role": "user", "content": followup}]
    assert "Partial derivatives" in captured[0]["content"]
    assert "BEGINNER" in captured[0]["content"]
    assert "Earlier calculus discussion" in captured[1]["content"]


def test_prompt_retains_only_recent_history():
    history = [{"role": "user", "content": f"Question {i}"} for i in range(15)]
    prompt = _build_messages("Follow up", "", "intermediate", history)
    assert prompt[1:-1] == history[-10:]
    assert prompt[-1] == {"role": "user", "content": "Follow up"}
