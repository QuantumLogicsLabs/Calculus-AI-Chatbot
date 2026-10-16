"""Make sure reported failures really fail test commands and quality gates."""
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from aiService.tests import chatbot_tests as evaluation
from aiService.tests import test_streaming_latency as latency


@pytest.mark.parametrize("checks,expected", [
    ((True, True, True, True), 0), ((False, True, True, True), 1),
    ((True, False, True, True), 1), ((True, True, False, True), 1),
    ((True, True, True, False), 1), ((), 1),
])
def test_acceptance_gate(checks, expected):
    assert evaluation.acceptance_exit_code(*checks) == expected


@pytest.mark.parametrize("text,valid", [
    (r"$$\boxed{3*x**2}$$", True), (r"$x$ and $$x**2$$", True),
    ("$$ $$", False), ("$ $", False), ("$x", False), (r"$\frac{x}{y$", False),
    (r"$x\, dx$", True), ("$x$ " + chr(92), False),
])
def test_latex_validator(text, valid):
    assert evaluation.check_latex_syntax_validity(text)[0] is valid


def test_word_limit_is_400():
    assert evaluation.check_word_count("word " * 400)[0]
    assert not evaluation.check_word_count("word " * 401)[0]


@pytest.mark.asyncio
async def test_mock_answers_fail_quality_gate_without_crashing(tmp_path, monkeypatch):
    question_file = tmp_path / "questions.json"
    question_file.write_text(json.dumps({"test_suite": "gate regression", "questions": [
        {"id": 1, "topic": "derivatives", "question": "Find the derivative of x**3", "answer_key": ["3*x**2"]},
        {"id": 2, "topic": "concepts", "question": "Explain derivatives"},
    ]}), encoding="utf-8")
    monkeypatch.setattr(evaluation, "QUESTIONS_FILE", question_file)
    monkeypatch.setattr(evaluation, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(evaluation, "OUTPUT_FILE", tmp_path / "report.json")
    cb2, cb9 = await evaluation.run_test_suite()
    assert not cb2 and not cb9
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["failed"] == 2


@pytest.mark.parametrize("name", [
    "test_cache_key_differs_with_different_history",
    "test_cache_key_stable_for_identical_history",
    "test_cache_key_stable_beyond_history_window",
])
def test_existing_cache_regressions(name):
    passed, reason = getattr(evaluation, name)()
    assert passed, reason


@pytest.mark.asyncio
@pytest.mark.parametrize("name", [
    "test_end_to_end_no_cache_collision_across_conversations",
    "test_end_to_end_repeat_followup_still_hits_cache",
    "test_end_to_end_history_growth_within_conversation",
])
async def test_existing_async_cache_regressions(name):
    passed, reason = await getattr(evaluation, name)()
    assert passed, reason


@pytest.mark.asyncio
async def test_empty_stream_fails_latency(monkeypatch):
    async def empty_stream(**kwargs):
        yield ""
    monkeypatch.setattr(latency, "ask_llm_stream", empty_stream)
    result = await latency.measure_first_token("Explain limits")
    assert result["passed"] is False
    assert latency.latency_exit_code([result]) == 1


@pytest.mark.asyncio
async def test_late_first_token_fails_latency(monkeypatch):
    async def late_stream(**kwargs):
        yield "A late token"

    ticks = iter([0.0, 2.1, 2.2])
    monkeypatch.setattr(latency, "ask_llm_stream", late_stream)
    monkeypatch.setattr(latency, "time", SimpleNamespace(perf_counter=lambda: next(ticks)))
    result = await latency.measure_first_token("Explain limits")
    assert result["first_token_seconds"] == 2.1
    assert not result["passed"]


def test_mock_quality_cli_exits_nonzero(tmp_path):
    # runpy exercises the actual __main__ exit path; inherited conftest env
    # guarantees mock mode, so this cannot use real provider credits.
    result = subprocess.run([
        sys.executable, "-B", "-c",
        "import os,runpy; os.environ['CALCVOYAGER_TEST_RESULTS_DIR']=" + repr(str(tmp_path)) +
        "; runpy.run_module('aiService.tests.chatbot_tests',run_name='__main__')",
    ], capture_output=True, text=True, encoding="utf-8", timeout=45)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "SOME CRITERIA NOT MET" in result.stdout
    assert (tmp_path / "test_results.json").exists()
    assert (tmp_path / "scope_results.json").exists()
