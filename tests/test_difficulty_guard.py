"""
Regression tests for CB-18 adaptive difficulty guard.

_build_system_content must normalise blank or unrecognised difficulty values
to "intermediate" so the DIFFICULTY_GUIDANCE lookup never silently degrades
(e.g. when the client sends difficulty="" or a typo like "medium").
"""

import pytest

from aiService.services.llm_client import _build_system_content, DIFFICULTY_GUIDANCE


@pytest.mark.parametrize("bad_difficulty", [
    "",          # empty string sent by client
    "   ",       # whitespace-only (not stripped by caller)
    "medium",    # unrecognised value
    "BEGINNER",  # wrong case
    "0",         # numeric string
])
def test_build_system_content_bad_difficulty_falls_back_to_intermediate(bad_difficulty):
    """Any blank or unrecognised difficulty string must produce the
    INTERMEDIATE guidance block without raising a KeyError."""
    content = _build_system_content("Limits", bad_difficulty)
    intermediate_marker = "ADAPTIVE DIFFICULTY: INTERMEDIATE"
    assert intermediate_marker in content, (
        f"Expected INTERMEDIATE guidance for difficulty={bad_difficulty!r} "
        f"but marker not found in output."
    )
    # Neither BEGINNER nor ADVANCED must appear when falling back.
    assert "ADAPTIVE DIFFICULTY: BEGINNER" not in content
    assert "ADAPTIVE DIFFICULTY: ADVANCED" not in content


@pytest.mark.parametrize("difficulty,expected_marker", [
    ("beginner",    "ADAPTIVE DIFFICULTY: BEGINNER"),
    ("intermediate","ADAPTIVE DIFFICULTY: INTERMEDIATE"),
    ("advanced",    "ADAPTIVE DIFFICULTY: ADVANCED"),
])
def test_build_system_content_valid_difficulty_produces_correct_block(difficulty, expected_marker):
    """Each valid difficulty string must produce its own guidance block."""
    content = _build_system_content("Partial Derivatives", difficulty)
    assert expected_marker in content, (
        f"Expected {expected_marker!r} for difficulty={difficulty!r}"
    )


def test_build_system_content_empty_difficulty_does_not_raise():
    """Passing difficulty='' must never raise a KeyError."""
    try:
        _build_system_content("", "")
    except KeyError as exc:
        pytest.fail(f"KeyError raised for empty difficulty: {exc}")
