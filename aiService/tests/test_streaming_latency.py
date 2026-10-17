"""
CB-10 Acceptance Test: Streaming First-Token Latency
Tests that ask_openai_stream() / ask_llm_stream() delivers the first
token within 2 seconds, per CB-10's acceptance criteria.

Run with: python -m aiService.tests.test_streaming_latency
"""

import asyncio
import time
import pytest

from aiService.services.llm_client import ask_llm_stream

TARGET_FIRST_TOKEN_SECONDS = 2.0

TEST_MESSAGES = [
    {"message": "Explain what a partial derivative is.", "topic": ""},
    {"message": "Find the gradient of f(x,y) = x^2y + 3y", "topic": "Gradients"},
    {"message": "Walk me through Lagrange multipliers step by step.", "topic": ""},
]


async def measure_first_token(message: str, topic: str = "", history: list = None):
    """
    Streams a single response and measures:
    - time to first token
    - total time to completion
    - total token/chunk count
    """
    start = time.perf_counter()
    first_token_time = None
    chunk_count = 0
    full_text = ""

    async for token in ask_llm_stream(message=message, topic=topic, history=history):
        if not token:
            continue
        chunk_count += 1
        if first_token_time is None:
            first_token_time = time.perf_counter() - start
        full_text += token

    total_time = time.perf_counter() - start

    return {
        "message": message,
        "first_token_seconds": round(first_token_time, 3) if first_token_time is not None else None,
        "total_seconds": round(total_time, 3),
        "chunk_count": chunk_count,
        "response_length_chars": len(full_text),
        "passed": first_token_time is not None and first_token_time < TARGET_FIRST_TOKEN_SECONDS,
    }


async def run_latency_suite():
    print(f"Running CB-10 streaming latency suite ({len(TEST_MESSAGES)} messages)")
    print(f"Target: first token under {TARGET_FIRST_TOKEN_SECONDS}s\n")

    results = []
    for i, test_case in enumerate(TEST_MESSAGES, start=1):
        result = await measure_first_token(**test_case)
        results.append(result)

        status = "PASS" if result["passed"] else "FAIL"
        print(f"[{i}] {status} — first token: {result['first_token_seconds']}s "
              f"| total: {result['total_seconds']}s "
              f"| chunks: {result['chunk_count']} "
              f"| \"{test_case['message'][:50]}\"")

    passed = sum(1 for r in results if r["passed"])
    print(f"\n{passed}/{len(results)} messages had first token under "
          f"{TARGET_FIRST_TOKEN_SECONDS}s")

    return results


def latency_exit_code(results):
    return 0 if results and all(result["passed"] for result in results) else 1


@pytest.mark.asyncio
@pytest.mark.parametrize("case", TEST_MESSAGES)
async def test_mock_first_token_latency(case):
    result = await measure_first_token(**case)
    assert result["passed"], result
    assert result["chunk_count"] > 1
    assert result["response_length_chars"] > 0


def test_latency_gate_rejects_failure_and_empty_results():
    assert latency_exit_code([{"passed": True}]) == 0
    assert latency_exit_code([{"passed": True}, {"passed": False}]) == 1
    assert latency_exit_code([]) == 1


if __name__ == "__main__":
    raise SystemExit(latency_exit_code(asyncio.run(run_latency_suite())))
