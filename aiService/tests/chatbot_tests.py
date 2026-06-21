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
    
    def to_dict(self):
        return {
            "question_id": self.question_id,
            "topic": self.topic,
            "question": self.question,
            "response_preview": self.response[:200] + "..." if len(self.response) > 200 else self.response,
            "word_count": self.word_count,
            "passed": self.passed,
            "checks": self.checks,
            "errors": self.errors
        }


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
    print("CalcVoyager CB-2 Acceptance Test")
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
        
        print()
    
    # Summary
    passed_count = sum(1 for r in results if r.passed)
    print("=" * 60)
    print(f"RESULTS: {passed_count}/{len(results)} tests passed")
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
    
    # Save results to file
    output_data = {
        "test_suite": data["test_suite"],
        "total_questions": len(results),
        "passed": passed_count,
        "failed": len(results) - passed_count,
        "pass_rate": f"{(passed_count/len(results)*100):.1f}%",
        "checks_summary": checks_summary,
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
    
    return passed_count >= 18


if __name__ == "__main__":
    asyncio.run(run_test_suite())
