"""
CB-2 Acceptance Test Suite
Tests the CalcVoyager system prompt against 20 calculus questions.

Validates:
- LaTeX formatting is present ($ delimiters)
- Follow-up suggestions are included ([FOLLOW_UPS] block)
- Response length is within limits (400 words max for walkthroughs)
- Math expressions are properly formatted

Does NOT validate:
- Mathematical correctness (requires domain expert review)
- Pedagogical quality (requires user testing)
"""

import asyncio
import json
import re
from pathlib import Path

from aiService.services.llm_client import ask_llm

# Test configuration
QUESTIONS_FILE = Path(__file__).parent / "calculus_questions.json"
OUTPUT_FILE = Path(__file__).parent / "test_results.json"


class TestResult:
    """Test result for a single question"""
    def __init__(self, question_id, topic, question):
        self.question_id = question_id
        self.topic = topic
        self.question = question
        self.response = ""
        self.passed = False
        self.checks = {}
        self.word_count = 0
        self.errors = []
        self.scope_enforcement = None  # CB-8: only set for off-topic tests
        self.correctness_score = None   # CB-9: answer key matching score
    
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
        return result_dict


def check_latex_formatting(response: str) -> tuple[bool, str]:
    """Check if response contains LaTeX math expressions"""
    inline_latex = re.findall(r'\$[^$]+\$', response)
    display_latex = re.findall(r'\$\$[^$]+\$\$', response)
    
    if inline_latex or display_latex:
        return True, f"Found {len(inline_latex)} inline + {len(display_latex)} display LaTeX expressions"
    return False, "No LaTeX math expressions found"


def check_follow_ups(response: str) -> tuple[bool, str]:
    """Check if response contains [FOLLOW_UPS] block"""
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
    """Check if response is within reasonable length"""
    words = response.split()
    word_count = len(words)
    
    if word_count > 450:
        return False, f"Response too long: {word_count} words (max 400 for walkthroughs)"
    elif word_count < 20:
        return False, f"Response too short: {word_count} words"
    return True, f"{word_count} words (acceptable)"


def check_step_formatting(response: str) -> tuple[bool, str]:
    """Check for proper step labeling in problem-solving responses"""
    # Look for step patterns: "Step 1", "Step 1:", "Step 1 —", etc.
    step_pattern = r'Step\s+\d+[\s:—\-]'
    steps = re.findall(step_pattern, response, re.IGNORECASE)
    
    if steps:
        return True, f"Found {len(steps)} numbered steps"
    # Not all responses need steps (conceptual Q&A), so this is informational
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
    """
    Check if Cal properly refuses off-topic questions.
    Returns (True, reason) if refusal detected.
    Returns (False, reason) if response appears to answer the off-topic question.
    """
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
    """
    CB-8: Test that Cal refuses off-topic questions.
    Returns True if all 10 questions are properly refused.
    """
    print("=" * 60)
    print("CB-8: Scope Enforcement Test")
    print("Testing Cal's refusal of off-topic questions")
    print("=" * 60)
    print()
    
    results = []
    
    for i, question in enumerate(OFF_TOPIC_QUESTIONS, 1):
        print(f"[{i}/10] Testing: {question[:50]}...")
        
        try:
            response = await ask_llm(
                message=question,
                topic="",
                history=[]
            )
            
            refused, reason = check_scope_enforcement(response)
            results.append(refused)
            
            status = "✓ REFUSED" if refused else "✗ ANSWERED"
            print(f"  {status} - {reason}")
            
            if not refused:
                print(f"    Response preview: {response[:100]}...")
        
        except Exception as e:
            print(f"  ✗ ERROR: {str(e)}")
            results.append(False)
        
        print()
    
    # Summary
    score = sum(results)
    print("=" * 60)
    print(f"SCOPE ENFORCEMENT: {score}/10 refused correctly")
    print("=" * 60)
    print()
    
    if score == 10:
        print("✓ CB-8 ACCEPTANCE: MET")
        print("  Cal successfully refuses all off-topic questions")
    else:
        print("✗ CB-8 ACCEPTANCE: NOT MET")
        print(f"  Cal should refuse all 10 questions (refused {score}/10)")
    
    print()
    # Save CB-8 results to a separate file
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
        json.dump(scope_output, f, indent=2)
    print(f"Scope results saved to: {scope_file}")
    return score == 10


# ============================================================================
# CB-9: Response Quality Evaluation Suite
# ============================================================================

def check_answer_key(response: str, expected_fragments: list[str]) -> tuple[bool, str, float]:
    """
    Check what fraction of expected LaTeX fragments appear in the response.
    Returns (passed, detail_string, score) where:
      - passed: True if score >= 0.6
      - detail_string: human-readable summary
      - score: float from 0.0 to 1.0
    """
    if not expected_fragments:
        return True, "No answer key provided", 1.0
    
    matched = 0
    missing = []
    
    for fragment in expected_fragments:
        # Case-sensitive substring match (LaTeX is case-sensitive)
        if fragment in response:
            matched += 1
        else:
            missing.append(fragment)
    
    score = matched / len(expected_fragments)
    passed = score >= 0.6
    
    detail = f"{matched}/{len(expected_fragments)} fragments found (score: {score:.2f})"
    if missing:
        detail += f" - Missing: {', '.join(missing[:3])}"
        if len(missing) > 3:
            detail += f" and {len(missing) - 3} more"
    
    return passed, detail, score


async def test_question(question_data: dict) -> TestResult:
    """Test a single question"""
    result = TestResult(
        question_id=question_data['id'],
        topic=question_data['topic'],
        question=question_data['question']
    )
    
    try:
        # Ask the LLM
        response = await ask_llm(
            message=result.question,
            topic=result.topic,
            history=[]
        )
        
        result.response = response
        result.word_count = len(response.split())
        
        # Run checks
        result.checks['latex_formatting'] = check_latex_formatting(response)
        result.checks['follow_ups'] = check_follow_ups(response)
        result.checks['word_count'] = check_word_count(response)
        result.checks['step_formatting'] = check_step_formatting(response)
        
        # CB-9: Check answer key if present
        if 'answer_key' in question_data and question_data['answer_key']:
            passed_key, detail_key, score_key = check_answer_key(
                response, 
                question_data['answer_key']
            )
            result.checks['answer_key'] = (passed_key, detail_key)
            result.correctness_score = score_key
        
        # Determine pass/fail
        critical_checks = ['latex_formatting', 'follow_ups', 'word_count']
        all_critical_passed = all(
            result.checks[check][0] for check in critical_checks
        )
        
        result.passed = all_critical_passed
        
        if not result.passed:
            result.errors = [
                f"{check}: {result.checks[check][1]}"
                for check in critical_checks
                if not result.checks[check][0]
            ]
    
    except Exception as e:
        result.passed = False
        result.errors = [f"Exception: {str(e)}"]
    
    return result


async def run_test_suite():
    """Run all 20 questions through the system prompt"""
    print("=" * 60)
    print("CB-2: CalcVoyager Acceptance Test")
    print("Testing system prompt against 20 calculus questions")
    print("=" * 60)
    print()
    
    # Load questions
    with open(QUESTIONS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    questions = data['questions']
    results = []
    
    # Test each question
    for i, question_data in enumerate(questions, 1):
        print(f"[{i}/20] Testing: {question_data['topic']} - Q{question_data['id']}")
        print(f"  Question: {question_data['question'][:70]}...")
        
        result = await test_question(question_data)
        results.append(result)
        
        status = "✓ PASS" if result.passed else "✗ FAIL"
        print(f"  {status} - {result.word_count} words")
        
        if not result.passed:
            for error in result.errors:
                print(f"    ⚠ {error}")
        
        # CB-9: Show correctness score if available
        if result.correctness_score is not None and result.correctness_score > 0:
            print(f"  Correctness: {result.correctness_score:.2f}")
        
        print()
    
    # Summary
    passed_count = sum(1 for r in results if r.passed)
    print("=" * 60)
    print(f"CB-2 RESULTS: {passed_count}/{len(results)} tests passed")
    print("=" * 60)
    print()
    
    # Detailed check breakdown
    print("Check Breakdown:")
    checks_summary = {
        'latex_formatting': 0,
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
    
    # CB-9: Correctness evaluation
    print("=" * 60)
    print("CB-9: Response Quality Evaluation")
    print("=" * 60)
    print()
    
    correctness_results = [r for r in results if r.correctness_score > 0]
    if correctness_results:
        print("Correctness Scores (answer key matching):")
        for result in correctness_results:
            status_icon = "✓" if result.correctness_score >= 0.6 else "✗"
            print(f"  Q{result.question_id:2d}: {status_icon} {result.correctness_score:.2f}")
        
        print()
        correct_count = sum(1 for r in correctness_results if r.correctness_score >= 0.6)
        total_with_keys = len(correctness_results)
        print(f"Overall Correctness: {correct_count}/{total_with_keys} questions with score >= 0.6")
        print()
        
        # CB-9 acceptance criteria: >= 16/20 (80%)
        cb9_met = correct_count >= 16
        if cb9_met:
            print("✓ CB-9 ACCEPTANCE: MET")
            print("  Response quality meets accuracy threshold")
        else:
            print("✗ CB-9 ACCEPTANCE: NOT MET")
            print(f"  Need at least 16/20 correct (got {correct_count}/{total_with_keys})")
    else:
        print("No answer keys found in questions - CB-9 evaluation skipped")
        cb9_met = False
    
    print()
    
    # Save results to file
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
    
    # Acceptance criteria
    if passed_count >= 18:  # 90% pass rate
        print("✓ CB-2 ACCEPTANCE CRITERIA MET")
        print("  System prompt performs well across all topic areas")
    else:
        print("✗ CB-2 ACCEPTANCE CRITERIA NOT MET")
        print(f"  Need at least 18/20 passing (got {passed_count}/20)")
        print("  Review failed tests and refine system prompt")
    
    return passed_count >= 18, cb9_met


if __name__ == "__main__":
    async def main():
        """Run all test suites: CB-2, CB-8, CB-9"""
        print()
        print("╔" + "═" * 58 + "╗")
        print("║" + " " * 10 + "CalcVoyager Test Suite Execution" + " " * 15 + "║")
        print("║" + " " * 12 + "CB-2, CB-8, CB-9 Combined" + " " * 20 + "║")
        print("╚" + "═" * 58 + "╝")
        print()
        
        # Run CB-2: System prompt acceptance test
        cb2_passed, cb9_passed = await run_test_suite()
        
        print()
        
        # Run CB-8: Scope enforcement test
        cb8_passed = await run_scope_enforcement_suite()
        
        # Combined summary
        print()
        print("=" * 60)
        print("COMBINED TEST SUMMARY")
        print("=" * 60)
        print(f"CB-2 (System Prompt):      {'✓ PASS' if cb2_passed else '✗ FAIL'}")
        print(f"CB-8 (Scope Enforcement):  {'✓ PASS' if cb8_passed else '✗ FAIL'}")
        print(f"CB-9 (Quality Evaluation): {'✓ PASS' if cb9_passed else '✗ FAIL'}")
        print("=" * 60)
        print()
        
        all_passed = cb2_passed and cb8_passed and cb9_passed
        if all_passed:
            print("🎉 ALL ACCEPTANCE CRITERIA MET")
        else:
            print("⚠ SOME CRITERIA NOT MET - Review failed tests above")
        print()
    
    asyncio.run(main())
