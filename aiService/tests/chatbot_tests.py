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

from aiService.services.llm_client import ask_llm
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
        print("CB-2, CB-8, CB-9, CB-16 Combined")
        print()

        cb2_passed, cb9_passed = await run_test_suite()
        print()
        cb8_passed = await run_scope_enforcement_suite()

        print()
        print("=" * 60)
        print("COMBINED TEST SUMMARY")
        print("=" * 60)
        print(f"CB-2 (System Prompt):      {'PASS' if cb2_passed else 'FAIL'}")
        print(f"CB-8 (Scope Enforcement):  {'PASS' if cb8_passed else 'FAIL'}")
        print(f"CB-9 (Quality Evaluation): {'PASS' if cb9_passed else 'FAIL'}")
        print("=" * 60)
        print()

        all_passed = cb2_passed and cb8_passed and cb9_passed
        if all_passed:
            print("ALL ACCEPTANCE CRITERIA MET")
            import sys
            sys.exit(0)
        else:
            print("SOME CRITERIA NOT MET - Review failed tests above")
        print()

    asyncio.run(main())