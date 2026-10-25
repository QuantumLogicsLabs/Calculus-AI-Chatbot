"""Tests for prompt engineering and system prompt construction in the calculus tutor."""
import pytest

from aiService.services.llm_client import (
    CAL_SYSTEM_PROMPT,
    DIFFICULTY_GUIDANCE,
    _build_system_content,
    _build_messages,
)


def test_system_prompt_defines_tutoring_vs_solving_modes():
    """Verify that CAL_SYSTEM_PROMPT explicitly differentiates between
    concept tutoring and direct problem solving."""
    prompt = CAL_SYSTEM_PROMPT
    assert "CONCEPT TUTORING" in prompt
    assert "PROBLEM SOLVING" in prompt
    assert r"Do NOT force an arbitrary computation or artificial \boxed{...} answer" in prompt
    assert r"The final mathematical result MUST be in boxed display LaTeX" in prompt


def test_system_prompt_defines_anti_hallucination_and_latex_rules():
    """Verify core anti-hallucination and formatting guidelines exist."""
    prompt = CAL_SYSTEM_PROMPT
    assert "ANTI-HALLUCINATION RULES" in prompt
    assert "MATHEMATICAL FORMATTING — LATEX RULES" in prompt
    assert "THINGS YOU MUST NEVER DO" in prompt
    assert "Force an artificial calculation or boxed numerical result onto a purely conceptual question" in prompt


@pytest.mark.parametrize("topic", [
    "Partial Derivatives",
    "Multiple Integrals",
])
def test_build_system_content_includes_topic_page_context(topic):
    """Page context tags should be appended when a topic is specified."""
    content = _build_system_content(topic, "intermediate")
    assert f"\n\n[PAGE CONTEXT: {topic}]" in content


def test_build_system_content_without_topic_omits_appended_tag():
    """When topic is empty, no extra page context tag is appended."""
    content_no_topic = _build_system_content("", "intermediate")
    content_with_topic = _build_system_content("Vectors", "intermediate")
    assert "[PAGE CONTEXT: Vectors]" in content_with_topic
    assert "[PAGE CONTEXT: Vectors]" not in content_no_topic


@pytest.mark.parametrize("difficulty,expected_needle", [
    ("beginner", "ADAPTIVE DIFFICULTY: BEGINNER"),
    ("intermediate", "ADAPTIVE DIFFICULTY: INTERMEDIATE"),
    ("advanced", "ADAPTIVE DIFFICULTY: ADVANCED"),
    ("unknown_tier", "ADAPTIVE DIFFICULTY: INTERMEDIATE"),
])
def test_build_system_content_injects_difficulty_guidance(difficulty, expected_needle):
    """Appropriate difficulty guidance should be appended, defaulting to intermediate."""
    content = _build_system_content("Gradients", difficulty)
    assert expected_needle in content


def test_build_messages_structure_with_summary_and_history():
    """_build_messages should assemble system prompt, summary, truncated history, and the user prompt."""
    history = [
        {"role": "user", "content": "What is a gradient?"},
        {"role": "assistant", "content": "It is a vector of partial derivatives."},
    ]
    summary = "Student was introduced to gradients."
    messages = _build_messages(
        message="Why is it perpendicular to level curves?",
        topic="Gradients",
        difficulty="beginner",
        history=history,
        summary=summary,
    )
    assert messages[0]["role"] == "system"
    assert "CONCEPT TUTORING" in messages[0]["content"]
    assert "[PAGE CONTEXT: Gradients]" in messages[0]["content"]
    assert "ADAPTIVE DIFFICULTY: BEGINNER" in messages[0]["content"]
    assert messages[1] == {"role": "system", "content": f"Earlier in this session: {summary}"}
    assert messages[2:4] == history
    assert messages[4] == {"role": "user", "content": "Why is it perpendicular to level curves?"}


def test_system_prompt_has_response_length_enforcement_section():
    """CAL_SYSTEM_PROMPT must contain a dedicated RESPONSE-LENGTH ENFORCEMENT
    section that names all three word-count ceilings explicitly.  This prevents
    the AI from silently drifting past the soft limits stated only in the
    response-structure list."""
    prompt = CAL_SYSTEM_PROMPT
    assert "RESPONSE-LENGTH ENFORCEMENT" in prompt, (
        "Missing RESPONSE-LENGTH ENFORCEMENT section in CAL_SYSTEM_PROMPT"
    )
    # All three ceiling values must appear verbatim.
    assert "150 words" in prompt, "150-word ceiling missing from enforcement section"
    assert "250 words" in prompt, "250-word ceiling missing from enforcement section"
    assert "400 words" in prompt, "400-word ceiling missing from enforcement section"
    # The section must instruct trimming, not just state the limits.
    assert "trim" in prompt.lower(), (
        "Enforcement section must tell the model to trim over-length drafts"
    )
