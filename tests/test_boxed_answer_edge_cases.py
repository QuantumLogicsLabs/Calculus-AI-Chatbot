"""
Regression tests for extract_boxed_answer edge cases.

These tests cover behaviors not already exercised in test_math_verifier.py:
- Nested braces (e.g. \frac{1}{2} inside \boxed{})
- Internal whitespace
- Trailing semicolon
- No \boxed{} → None
- Multiple \boxed{} — first wins
- z = ... LHS prefix stripping
- Empty or whitespace-only box content
"""

import pytest

from aiService.services.math_verifier import extract_boxed_answer, verify_cal_math


@pytest.mark.parametrize("raw_response,expected_extracted", [
    # Nested braces preserved (regex supports one level of brace nesting)
    (r"\boxed{\frac{1}{2}}", r"\frac{1}{2}"),
    # Internal whitespace stripped
    (r"\boxed{  3*x**2  }", "3*x**2"),
    # Trailing semicolon stripped (same as . and ,)
    (r"\boxed{2*x;}", "2*x"),
    # LHS prefix with variable 'z' stripped
    (r"\boxed{z = 3*t}", "3*t"),
    # First of multiple \boxed{} expressions is extracted
    (r"\boxed{x^3} + \boxed{2}", "x^3"),
    # Double-dollar delimiters inside the box are stripped
    (r"\boxed{$$2*x$$}", "2*x"),
])
def test_extract_boxed_answer_additional_edge_cases(raw_response, expected_extracted):
    """extract_boxed_answer must handle nested braces, whitespace, semicolons,
    multiple boxes, and double-dollar delimiters correctly."""
    assert extract_boxed_answer(raw_response) == expected_extracted


def test_extract_boxed_answer_returns_none_when_no_box():
    """When the response contains no \\boxed{} at all, None must be returned."""
    assert extract_boxed_answer("The derivative of x^2 is 2x.") is None


@pytest.mark.parametrize("raw_response", [
    r"\boxed{}",       # Empty braces
    r"\boxed{   }",   # Whitespace-only content
])
def test_extract_boxed_answer_empty_or_whitespace_box_is_falsy(raw_response):
    r"""An empty or whitespace-only \boxed{} returns an empty string (falsy).

    The verify_cal_math caller guards with 'if not cal_answer' which treats
    both None and '' as 'no answer found', so the falsy return is safe.
    This test documents the current behaviour to catch any future regression
    that accidentally changes the return type.
    """
    result = extract_boxed_answer(raw_response)
    assert not result, (
        f"Expected falsy value for empty box, got {result!r}"
    )


def test_verify_cal_math_treats_empty_box_as_no_answer():
    r"""verify_cal_math must return (None, None, error_message) when the box is empty,
    because extract_boxed_answer returns a falsy empty string."""
    correct, sympy_result, diagnostic = verify_cal_math(
        "Find the derivative of x^2", r"\boxed{}"
    )
    assert correct is None
    assert sympy_result is None
    assert diagnostic  # non-empty error message


def test_verify_cal_math_nested_frac_box_is_not_verifiable_by_sympy():
    r"""An answer in \boxed{\frac{1}{2}} extracts correctly but \frac LaTeX
    is not parseable by the SymPy preprocessor, so the verdict is None
    (unverifiable), NOT False (wrong answer).

    This prevents a false 'incorrect' verdict for valid-but-unparseable answers.
    """
    question = "Find the integral of x dx from 0 to 1"
    boxed = r"\boxed{\frac{1}{2}}"
    correct, sympy_result, diagnostic = verify_cal_math(question, boxed)
    # The SymPy result for x^2/2 from 0 to 1 is 1/2.
    assert sympy_result == "1/2", (
        f"Expected SymPy result '1/2' but got {sympy_result!r}"
    )
    # The extracted \frac{1}{2} cannot be parsed, so verdict must be None not False.
    assert correct is None, (
        f"Expected None (unverifiable) but got correct={correct!r}. "
        f"diagnostic={diagnostic!r}"
    )

