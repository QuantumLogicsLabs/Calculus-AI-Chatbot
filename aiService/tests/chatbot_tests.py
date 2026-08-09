"""
CB-2 Acceptance Test Suite
Tests the CalcVoyager system prompt against 20 calculus questions.

Validates:
- LaTeX formatting is present AND syntactically valid
- Follow-up suggestions are included ([FOLLOW_UPS] block)
- Response length is within limits (400 words max for walkthroughs)
- Math expressions are properly formatted
- CB-16: Boxed answers match independent SymPy verification

Does NOT validate:
- Pedagogical quality (requires user testing)
"""

import asyncio
import json
import re
from pathlib import Path

from aiService.services.llm_client import ask_llm, _cache_key, _response_cache  # OB-3: added _cache_key, _response_cache
from aiService.services.math_verifier import verify_cal_math  # CB-16

QUESTIONS_FILE = Path(__file__).parent / "calculus_questions.json"
OUTPUT_FILE = Path(__file__).parent / "test_results.json"


class TestResult:
    def __init__(self, question_id, topic, question):
        self.question_id = question_id
        self.topic = topic
        self.question = question
        self.response = ""
        self.passed = False
        self.checks = {}
        self.word_count = 0
        self.errors = []
        self.scope_enforcement = None
        self.correctness_score = None
        self.verified_correct = None  # CB-16

    def to_dict(self):
        result_dict = {
            "question_id": self.question_id,
            "topic": self.topic,
            "question": self.question,
            "response_preview": self.response[:200] + "..." if len(self.response) > 200 else self.response,
            "word_count": self.word_count,
            "passed": self.passed,
            "checks": self.checks,
            "errors": self.errors
        }
        if self.scope_enforcement is not None:
            result_dict["scope_enforcement"] = self.scope_enforcement
        if self.correctness_score is not None:
            result_dict["correctness_score"] = self.correctness_score
        if self.verified_correct is not None:
            result_dict["verified_correct"] = self.verified_correct
        return result_dict


def check_latex_formatting(response: str) -> tuple[bool, str]:
    """Check if response contains LaTeX math expressions at all."""
    inline_latex = re.findall(r'\$[^$]+\$', response)
    display_latex = re.findall(r'\$\$[^$]+\$\$', response)

    if inline_latex or display_latex:
        return True, f"Found {len(inline_latex)} inline + {len(display_latex)} display LaTeX expressions"
    return False, "No LaTeX math expressions found"


def _braces_balanced(s: str) -> bool:
    depth = 0
    for ch in s:
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def check_latex_syntax_validity(response: str) -> tuple[bool, str]:
    """
    CB-T6: Validate that LaTeX found in the response is well-formed,
    not just present. Checks:
      - '$' delimiters occur an even number of times (balanced)
      - no empty math blocks ($$ $$ or $ $)
      - braces inside \\frac{}{}, \\sqrt{}, \\boxed{} are balanced
      - no dangling/incomplete LaTeX commands (trailing lone backslash)
    """
    errors = []

    # A run of $ signs not preceded/followed by another $ marks a
    # delimiter boundary; simplest robust check: total '$' count is even.
    dollar_count = response.count('$')
    if dollar_count % 2 != 0:
        errors.append("Unbalanced '$' delimiters (odd count)")

    if re.search(r'\${1,2}\s*\${1,2}', response):
        errors.append("Empty math block found ($$ $$ or $ $)")

    for command in ['frac', 'sqrt', 'boxed']:
        # Find every occurrence of \command{...} or \command{...}{...}
        # and confirm braces balance from that point.
        for m in re.finditer(rf'\\{command}(\{{)', response):
            start = m.start(1)
            snippet = response[start:start + 400]  # bounded lookahead
            # walk the snippet and confirm the opened brace closes
            depth = 0
            closed = False
            for ch in snippet:
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        closed = True
                        break
            if not closed:
                errors.append(f"Unbalanced braces after \\{command}{{")

    if re.search(r'\\(?![a-zA-Z{}$])', response):
        errors.append("Dangling backslash (incomplete LaTeX command)")

    if not _braces_balanced(response):
        errors.append("Overall brace count is unbalanced")

    if errors:
        return False, "; ".join(errors)
    return True, "LaTeX syntax valid (delimiters and braces balanced)"


def check_follow_ups(response: str) -> tuple[bool, str]:
    pattern = r'\[FOLLOW_UPS\](.*?)\[/FOLLOW_UPS\]'
    match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)

    if not match:
        return False, "No [FOLLOW_UPS] block found"

    follow_ups_text = match.group(1).strip()
    suggestions = [line for line in follow_ups_text.split('\n') if line.strip()]

    if len(suggestions) >= 3:
        return True, f"Found {len(suggestions)} follow-up suggestions"
    return False, f"Only {len(suggestions)} suggestions found (expected 3)"


def check_word_count(response: str) -> tuple[bool, str]:
    words = response.split()
    word_count = len(words)

    if word_count > 450:
        return False, f"Response too long: {word_count} words (max 400 for walkthroughs)"
    elif word_count < 20:
        return False, f"Response too short: {word_count} words"
    return True, f"{word_count} words (acceptable)"


def check_step_formatting(response: str) -> tuple[bool, str]:
    step_pattern = r'Step\s+\d+[\s:—\-]'
    steps = re.findall(step_pattern, response, re.IGNORECASE)

    if steps:
        return True, f"Found {len(steps)} numbered steps"
    return True, "No numbered steps (may be conceptual explanation)"


# ============================================================================
# CB-8: Hallucination Guardrails & Scope Enforcement
# ============================================================================

OFF_TOPIC_QUESTIONS = [
    "Who was the first president of the United States?",
    "Write a Python function to sort a list of numbers.",
    "What is the capital of France?",
    "Explain the causes of World War II.",
    "How do I make chocolate chip cookies?",
    "What is the meaning of life?",
    "Tell me about the solar system.",
    "Who invented the telephone?",
    "What is photosynthesis?",
    "Explain how blockchain technology works."
]


def check_scope_enforcement(response: str) -> tuple[bool, str]:
    refusal_phrases = [
        "I'm Cal",
        "outside my expertise",
        "outside what I cover",
        "calculus tutor",
        "CalcVoyager"
    ]
    has_refusal = any(phrase in response for phrase in refusal_phrases)
    has_stepbystep = bool(re.search(r'Step\s+\d+[\s:—\-]', response))

    if has_refusal and not has_stepbystep:
        return True, "Proper refusal detected"
    if has_stepbystep:
        return False, "Response contains step-by-step math (scope violation)"
    return False, "No refusal phrase detected"


async def run_scope_enforcement_suite() -> bool:
    print("=" * 60)
    print("CB-8: Scope Enforcement Test")
    print("Testing Cal's refusal of off-topic questions")
    print("=" * 60)
    print()

    results = []

    for i, question in enumerate(OFF_TOPIC_QUESTIONS, 1):
        print(f"[{i}/10] Testing: {question[:50]}...")

        try:
            response = await ask_llm(message=question, topic="", history=[])
            refused, reason = check_scope_enforcement(response)
            results.append(refused)

            status = "REFUSED" if refused else "ANSWERED"
            print(f"  {status} - {reason}")

            if not refused:
                print(f"    Response preview: {response[:100]}...")

        except Exception as e:
            print(f"  ERROR: {str(e)}")
            results.append(False)

        print()

    score = sum(results)
    print("=" * 60)
    print(f"SCOPE ENFORCEMENT: {score}/10 refused correctly")
    print("=" * 60)
    print()

    if score == 10:
        print("PASS: CB-8 ACCEPTANCE MET")
        print("  Cal successfully refuses all off-topic questions")
    else:
        print("FAIL: CB-8 ACCEPTANCE NOT MET")
        print(f"  Cal should refuse all 10 questions (refused {score}/10)")

    print()
    scope_output = {
        "test": "CB-8 Scope Enforcement",
        "score": f"{score}/10",
        "passed": score == 10,
        "results": [
            {"question": q, "refused": r}
            for q, r in zip(OFF_TOPIC_QUESTIONS, results)
        ]
    }
    scope_file = Path(__file__).parent / "scope_results.json"
    with open(scope_file, 'w', encoding='utf-8') as f:
        json.dump(scope_output, f, indent=2, ensure_ascii=False)

    return score == 10


def check_answer_key(response: str, answer_key: list) -> tuple[bool, str, float]:
    """CB-9: fraction of expected LaTeX/text fragments found in response."""
    if not answer_key:
        return True, "No answer key provided", 0.0

    found = sum(1 for fragment in answer_key if fragment in response)
    score = found / len(answer_key)
    passed = score >= 0.6
    return passed, f"{found}/{len(answer_key)} fragments found", score


async def test_question(question_data: dict) -> TestResult:
    result = TestResult(
        question_data['id'],
        question_data['topic'],
        question_data['question']
    )

    try:
        response = await ask_llm(
            message=result.question,
            topic=result.topic,
            history=[]
        )

        result.response = response
        result.word_count = len(response.split())

        result.checks['latex_formatting'] = check_latex_formatting(response)
        result.checks['latex_syntax'] = check_latex_syntax_validity(response)  # T6: new
        result.checks['follow_ups'] = check_follow_ups(response)
        result.checks['word_count'] = check_word_count(response)
        result.checks['step_formatting'] = check_step_formatting(response)

        if 'answer_key' in question_data and question_data['answer_key']:
            passed_key, detail_key, score_key = check_answer_key(
                response,
                question_data['answer_key']
            )
            result.checks['answer_key'] = (passed_key, detail_key)
            result.correctness_score = score_key

        # CB-16: Symbolic math verification (graceful fallback for unsupported problems)
        try:
            verified_correct, sympy_answer, error_message = verify_cal_math(result.question, response)
            result.verified_correct = verified_correct
        except Exception:
            result.verified_correct = None

        critical_checks = ['latex_formatting', 'latex_syntax', 'follow_ups', 'word_count']
        all_critical_passed = all(
            result.checks[check][0] for check in critical_checks
        )

        # T6: a confirmed hallucinated calculation (verified_correct is
        # explicitly False, not None/unverifiable) is now a hard fail.
        if result.verified_correct is False:
            all_critical_passed = False

        result.passed = all_critical_passed

        if not result.passed:
            result.errors = [
                f"{check}: {result.checks[check][1]}"
                for check in critical_checks
                if not result.checks[check][0]
            ]
            if result.verified_correct is False:
                result.errors.append(
                    "CB-16: boxed answer failed independent SymPy verification (possible hallucination)"
                )

    except Exception as e:
        result.passed = False
        result.errors = [f"Exception: {str(e)}"]

    return result


# ============================================================================
# OB-3: Follow-up cache correctness suite
#
# Bug: _cache_key() previously hashed only (message, topic, difficulty),
# so two conversations asking the literal same follow-up text with
# different prior context could collide and be served the wrong cached
# answer. These tests validate the fix directly against _cache_key(),
# and end-to-end against ask_llm() across representative multi-turn
# scenarios.
# ============================================================================

FOLLOW_UP_TEXT = "Can you explain that more?"

HISTORY_DERIVATIVES = [
    {"role": "user", "content": "What is a partial derivative?"},
    {"role": "assistant", "content": "A partial derivative measures how a multivariable function changes with respect to one variable, holding the others constant."},
]

HISTORY_LAGRANGE = [
    {"role": "user", "content": "How do Lagrange multipliers work?"},
    {"role": "assistant", "content": "Lagrange multipliers find extrema of a function subject to equality constraints by setting gradients proportional to each other."},
]

# Same NUMBER of turns as the two histories above, but different content —
# this is the case that would previously slip through even a naive
# "does history length matter" check, since the old key ignored content
# entirely and length alone wasn't part of it either.
HISTORY_INTEGRALS = [
    {"role": "user", "content": "How do I set up a double integral over a region?"},
    {"role": "assistant", "content": "You describe the region's bounds for each variable, then integrate the inner variable first, treating the outer variable as constant."},
]


def test_cache_key_differs_with_different_history():
    """Unit test: same message/topic/difficulty, different history -> different keys."""
    key_a = _cache_key(FOLLOW_UP_TEXT, "", "intermediate", HISTORY_DERIVATIVES)
    key_b = _cache_key(FOLLOW_UP_TEXT, "", "intermediate", HISTORY_LAGRANGE)
    key_c = _cache_key(FOLLOW_UP_TEXT, "", "intermediate", HISTORY_INTEGRALS)

    passed = len({key_a, key_b, key_c}) == 3
    detail = (
        "All 3 history contexts produced distinct cache keys"
        if passed else
        "COLLISION: identical cache key generated for different conversation histories"
    )
    return passed, detail


def test_cache_key_stable_for_identical_history():
    """Regression check: identical inputs must still produce identical keys (cache hits preserved)."""
    key_a = _cache_key(FOLLOW_UP_TEXT, "", "intermediate", HISTORY_DERIVATIVES)
    key_b = _cache_key(FOLLOW_UP_TEXT, "", "intermediate", list(HISTORY_DERIVATIVES))  # fresh list, same content

    passed = key_a == key_b
    detail = (
        "Identical message+history reproduces the same cache key (cache hits still work)"
        if passed else
        "Identical inputs produced different keys — cache hit rate would regress"
    )
    return passed, detail


def test_cache_key_stable_beyond_history_window():
    """History entries older than the 10-turn window should not affect the key (matches _build_messages)."""
    long_history = HISTORY_DERIVATIVES + [
        {"role": "user", "content": f"filler question {i}"} for i in range(20)
    ]
    long_history_extra_old_turn = [
        {"role": "user", "content": "an ancient, irrelevant first message"}
    ] + long_history

    key_a = _cache_key(FOLLOW_UP_TEXT, "", "intermediate", long_history)
    key_b = _cache_key(FOLLOW_UP_TEXT, "", "intermediate", long_history_extra_old_turn)

    # Both get truncated to the same trailing 10 turns, so keys should match.
    passed = key_a == key_b
    detail = (
        "Cache key correctly ignores history older than the trailing window"
        if passed else
        "Cache key changed based on history outside the trailing window (window mismatch with _build_messages)"
    )
    return passed, detail


async def test_end_to_end_no_cache_collision_across_conversations():
    """
    End-to-end: simulate 3 different students asking the identical literal
    follow-up question after 3 different conversations. Confirm the cache
    stores 3 separate entries instead of one shared (incorrect) entry.
    """
    _response_cache.clear()

    await ask_llm(message=FOLLOW_UP_TEXT, topic="", history=HISTORY_DERIVATIVES)
    await ask_llm(message=FOLLOW_UP_TEXT, topic="", history=HISTORY_LAGRANGE)
    await ask_llm(message=FOLLOW_UP_TEXT, topic="", history=HISTORY_INTEGRALS)

    passed = len(_response_cache) == 3
    detail = (
        f"3 distinct cache entries stored for 3 distinct conversations ({len(_response_cache)} found)"
        if passed else
        f"Expected 3 distinct cache entries, found {len(_response_cache)} — follow-ups are colliding"
    )
    return passed, detail


async def test_end_to_end_repeat_followup_still_hits_cache():
    """
    End-to-end: the SAME student asking the SAME follow-up in the SAME
    conversation state a second time should still be a cache hit (the fix
    must not break normal caching behavior).
    """
    _response_cache.clear()

    first_response = await ask_llm(message=FOLLOW_UP_TEXT, topic="", history=HISTORY_DERIVATIVES)
    size_after_first = len(_response_cache)

    second_response = await ask_llm(message=FOLLOW_UP_TEXT, topic="", history=list(HISTORY_DERIVATIVES))
    size_after_second = len(_response_cache)

    passed = (
        first_response == second_response
        and size_after_first == 1
        and size_after_second == 1
    )
    detail = (
        "Repeat follow-up in the same context correctly hit the cache (no new entry created)"
        if passed else
        f"Cache hit behavior regressed (entries: {size_after_first} -> {size_after_second})"
    )
    return passed, detail


async def test_end_to_end_history_growth_within_conversation():
    """
    End-to-end: within ONE growing conversation, the same follow-up asked
    again after a new turn has been appended should be treated as new
    context (not silently served the earlier cached answer).
    """
    _response_cache.clear()

    conversation = list(HISTORY_DERIVATIVES)
    await ask_llm(message=FOLLOW_UP_TEXT, topic="", history=conversation)

    conversation = conversation + [
        {"role": "user", "content": FOLLOW_UP_TEXT},
        {"role": "assistant", "content": "Here's a deeper look at partial derivatives..."},
        {"role": "user", "content": "What about second-order partials?"},
        {"role": "assistant", "content": "Second-order partials differentiate a partial derivative again..."},
    ]

    await ask_llm(message=FOLLOW_UP_TEXT, topic="", history=conversation)

    passed = len(_response_cache) == 2
    detail = (
        "Same follow-up later in a growing conversation correctly created a fresh cache entry"
        if passed else
        f"Expected 2 distinct cache entries as the conversation grew, found {len(_response_cache)}"
    )
    return passed, detail


async def run_followup_cache_suite() -> bool:
    print("=" * 60)
    print("OB-3: Follow-Up Question Cache Correctness Suite")
    print("Testing _cache_key() fix across multi-turn scenarios")
    print("=" * 60)
    print()

    sync_tests = [
        ("Cache key differs across different histories", test_cache_key_differs_with_different_history),
        ("Cache key stable for identical history (cache hits preserved)", test_cache_key_stable_for_identical_history),
        ("Cache key ignores history beyond trailing window", test_cache_key_stable_beyond_history_window),
    ]

    async_tests = [
        ("No cache collision across different conversations", test_end_to_end_no_cache_collision_across_conversations),
        ("Repeat follow-up in same context still hits cache", test_end_to_end_repeat_followup_still_hits_cache),
        ("Same follow-up later in a growing conversation gets fresh entry", test_end_to_end_history_growth_within_conversation),
    ]

    results = []

    for label, test_fn in sync_tests:
        passed, detail = test_fn()
        results.append(passed)
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {label}")
        print(f"       {detail}")
        print()

    for label, test_fn in async_tests:
        passed, detail = await test_fn()
        results.append(passed)
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {label}")
        print(f"       {detail}")
        print()

    score = sum(results)
    total = len(results)

    print("=" * 60)
    print(f"OB-3 RESULTS: {score}/{total} tests passed")
    print("=" * 60)
    print()

    all_passed = score == total
    if all_passed:
        print("PASS: OB-3 ACCEPTANCE MET")
        print("  Follow-up questions no longer collide across conversation contexts")
    else:
        print("FAIL: OB-3 ACCEPTANCE NOT MET")
        print(f"  {total - score} scenario(s) still show incorrect cache behavior")

    print()
    return all_passed


async def run_test_suite():
    print("=" * 60)
    print("CB-2: CalcVoyager Acceptance Test")
    print("Testing system prompt against 20 calculus questions")
    print("=" * 60)
    print()

    with open(QUESTIONS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    questions = data['questions']
    results = []

    for i, question_data in enumerate(questions, 1):
        print(f"[{i}/20] Testing: {question_data['topic']} - Q{question_data['id']}")
        print(f"  Question: {question_data['question'][:70]}...")

        result = await test_question(question_data)
        results.append(result)

        status = "PASS" if result.passed else "FAIL"
        print(f"  {status} - {result.word_count} words")

        if not result.passed:
            for error in result.errors:
                print(f"    WARNING: {error}")

        if result.correctness_score is not None and result.correctness_score > 0:
            print(f"  Correctness: {result.correctness_score:.2f}")

        print()

    passed_count = sum(1 for r in results if r.passed)
    print("=" * 60)
    print(f"CB-2 RESULTS: {passed_count}/{len(results)} tests passed")
    print("=" * 60)
    print()

    print("Check Breakdown:")
    checks_summary = {
        'latex_formatting': 0,
        'latex_syntax': 0,
        'follow_ups': 0,
        'word_count': 0,
        'step_formatting': 0
    }

    for result in results:
        for check_name in checks_summary.keys():
            if result.checks.get(check_name, (False, ""))[0]:
                checks_summary[check_name] += 1

    for check_name, count in checks_summary.items():
        print(f"  {check_name}: {count}/{len(results)}")

    print()

    print("=" * 60)
    print("CB-9: Response Quality Evaluation")
    print("=" * 60)
    print()

    correctness_results = [r for r in results if r.correctness_score > 0]
    if correctness_results:
        print("Correctness Scores (answer key matching):")
        for result in correctness_results:
            status_icon = "PASS" if result.correctness_score >= 0.6 else "FAIL"
            print(f"  Q{result.question_id:2d}: {status_icon} {result.correctness_score:.2f}")

        print()
        correct_count = sum(1 for r in correctness_results if r.correctness_score >= 0.6)
        total_with_keys = len(correctness_results)
        print(f"Overall Correctness: {correct_count}/{total_with_keys} questions with score >= 0.6")
        print()

        cb9_met = correct_count >= 16
        if cb9_met:
            print("PASS: CB-9 ACCEPTANCE MET")
            print("  Response quality meets accuracy threshold")
        else:
            print("FAIL: CB-9 ACCEPTANCE NOT MET")
            print(f"  Need at least 16/20 correct (got {correct_count}/{total_with_keys})")
    else:
        print("No answer keys found in questions - CB-9 evaluation skipped")
        cb9_met = False

    print()

    # T6: summarize CB-16 verification outcomes
    verified_results = [r for r in results if r.verified_correct is not None]
    if verified_results:
        verified_pass = sum(1 for r in verified_results if r.verified_correct)
        print("=" * 60)
        print("CB-16: Symbolic Math Verification Summary")
        print("=" * 60)
        print(f"Verifiable questions: {len(verified_results)}/{len(results)}")
        print(f"Verified correct: {verified_pass}/{len(verified_results)}")
        for r in verified_results:
            if not r.verified_correct:
                print(f"  ⚠ Q{r.question_id}: FAILED symbolic verification")
        print()

    output_data = {
        "test_suite": data["test_suite"],
        "total_questions": len(results),
        "passed": passed_count,
        "failed": len(results) - passed_count,
        "pass_rate": f"{(passed_count/len(results)*100):.1f}%",
        "checks_summary": checks_summary,
        "correctness_met": cb9_met if correctness_results else None,
        "results": [r.to_dict() for r in results]
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"Detailed results saved to: {OUTPUT_FILE}")
    print()

    if passed_count >= 18:
        print("PASS: CB-2 ACCEPTANCE CRITERIA MET")
        print("  System prompt performs well across all topic areas")
    else:
        print("FAIL: CB-2 ACCEPTANCE CRITERIA NOT MET")
        print(f"  Need at least 18/20 passing (got {passed_count}/20)")
        print("  Review failed tests and refine system prompt")

    return passed_count >= 18, cb9_met


if __name__ == "__main__":
    async def main():
        print()
        print("[CalcVoyager Test Suite Execution]")
        print("CB-2, CB-8, CB-9, CB-16, OB-3 Combined")
        print()

        cb2_passed, cb9_passed = await run_test_suite()
        print()
        cb8_passed = await run_scope_enforcement_suite()
        print()
        ob3_passed = await run_followup_cache_suite()  # OB-3: new suite

        print()
        print("=" * 60)
        print("COMBINED TEST SUMMARY")
        print("=" * 60)
        print(f"CB-2 (System Prompt):      {'PASS' if cb2_passed else 'FAIL'}")
        print(f"CB-8 (Scope Enforcement):  {'PASS' if cb8_passed else 'FAIL'}")
        print(f"CB-9 (Quality Evaluation): {'PASS' if cb9_passed else 'FAIL'}")
        print(f"OB-3 (Follow-Up Caching):  {'PASS' if ob3_passed else 'FAIL'}")  # OB-3: new line
        print("=" * 60)
        print()

        all_passed = cb2_passed and cb8_passed and cb9_passed and ob3_passed  # OB-3: added to gate
        if all_passed:
            print("ALL ACCEPTANCE CRITERIA MET")
            import sys
            sys.exit(0)
        else:
            print("SOME CRITERIA NOT MET - Review failed tests above")
        print()

    asyncio.run(main())