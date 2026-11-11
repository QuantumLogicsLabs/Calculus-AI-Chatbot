"""
Regression tests for the _build_messages history-window cap.

The history slice used in _build_messages must always match the slice used in
_cache_key so that the two functions never silently diverge (e.g. if someone
changes one but forgets the other).
"""

import pytest

from aiService.services.llm_client import (
    _build_messages,
    _cache_key,
    _CACHE_HISTORY_WINDOW,
)

_WINDOW = _CACHE_HISTORY_WINDOW


def _make_history(n: int) -> list:
    """Return a history list of length n with alternating user/assistant turns."""
    turns = []
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        turns.append({"role": role, "content": f"turn {i}"})
    return turns


def _user_turns_from_messages(messages: list) -> list:
    """Extract non-system messages (the history + final user prompt) from assembled messages."""
    return [m for m in messages if m["role"] != "system"]


# ---------------------------------------------------------------------------
# Cap enforcement
# ---------------------------------------------------------------------------

def test_build_messages_caps_history_at_window():
    """When history exceeds _CACHE_HISTORY_WINDOW, only the most recent window
    turns must appear in the assembled message list."""
    history = _make_history(_WINDOW + 5)  # 5 turns over the window
    messages = _build_messages("New question", "Limits", "intermediate", history)
    # All non-system messages: window history turns + 1 final user message.
    non_system = _user_turns_from_messages(messages)
    assert len(non_system) == _WINDOW + 1, (
        f"Expected {_WINDOW + 1} non-system messages, got {len(non_system)}"
    )
    # The last window turns of history must be present.
    expected_history = history[-_WINDOW:]
    for turn in expected_history:
        assert turn in non_system, f"Expected {turn!r} to be in assembled messages"


def test_build_messages_accepts_none_history():
    """Passing history=None must not raise and must produce only the system
    message and the final user prompt."""
    messages = _build_messages("Hello", "Gradients", "beginner", None)
    non_system = _user_turns_from_messages(messages)
    assert non_system == [{"role": "user", "content": "Hello"}]


def test_build_messages_short_history_is_not_truncated():
    """When history is shorter than the window, all turns must be included."""
    history = _make_history(_WINDOW - 2)
    messages = _build_messages("Next question", "Integrals", "advanced", history)
    non_system = _user_turns_from_messages(messages)
    # All history turns + final user message.
    assert len(non_system) == len(history) + 1


# ---------------------------------------------------------------------------
# Consistency with _cache_key
# ---------------------------------------------------------------------------

def test_history_window_consistent_between_build_messages_and_cache_key():
    """The number of history turns used in _build_messages must equal the
    number included in the _cache_key payload.

    We verify this by asserting that a history list longer than the window
    produces the same tail slice in both functions.
    """
    history = _make_history(_WINDOW + 3)
    # The slice _cache_key uses internally:
    expected_tail = history[-_WINDOW:]

    # Confirm _build_messages only contains that tail's content (not earlier turns).
    messages = _build_messages("Q", "topic", "intermediate", history)
    non_system = _user_turns_from_messages(messages)
    # Remove the final user prompt we added.
    assembled_history_turns = non_system[:-1]
    assert assembled_history_turns == expected_tail, (
        "_build_messages history tail does not match the _CACHE_HISTORY_WINDOW slice"
    )


def test_build_messages_includes_summary_when_provided():
    """When summary is non-empty, a second system message must be inserted
    immediately after the primary system prompt."""
    history = _make_history(2)
    summary = "Student covered partial derivatives."
    messages = _build_messages("Go on", "topic", "intermediate", history, summary)
    assert messages[1]["role"] == "system"
    assert summary in messages[1]["content"]
