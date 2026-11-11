import pytest

from aiService.services.math_verifier import (
    verify_cal_math,
    preprocess_math_expr,
    _strip_differential,
    parse_operation,
    extract_boxed_answer,
)


@pytest.mark.parametrize("boxed,verdict", [
    (r"\boxed{cos(x)}", True),
    (r"\boxed{\cos(x)}", True),
    (r"\boxed{-\cos(x)}", False),
    (r"\boxed{unsupported\command{x}}", None),
])
def test_trigonometric_answers_and_unverifiable_notation(boxed, verdict):
    correct, expected, diagnostic = verify_cal_math("Find the derivative of sin(x)", boxed)
    assert correct is verdict
    assert expected == "cos(x)"
    if verdict is None:
        assert diagnostic


@pytest.mark.parametrize("raw,expected", [
    # Trailing 'dx' removed
    ("x**2 dx", "x**2"),
    # Trailing 'd x' with space removed
    ("sin(x) d x", "sin(x)"),
    # Trailing 'dy' removed
    ("x**2 + y dy", "x**2 + y"),
    # No differential — expression returned unchanged
    ("x**2 + 1", "x**2 + 1"),
    # 'as x → …' suffix removed (limit notation)
    ("1/x as x approaches infinity", "1/x"),
    ("sin(x)/x as x -> 0", "sin(x)/x"),
])
def test_strip_differential(raw, expected):
    """_strip_differential must remove trailing differential terms without
    altering the rest of the expression."""
    assert _strip_differential(raw) == expected


@pytest.mark.parametrize("question,expected_operation,expected_expr", [
    # 'dx' suffix must not appear in the extracted expression
    ("Find the integral of x^2 dx", "integral", "x^2"),
    ("Find the integral of sin(x) dx", "integral", "sin(x)"),
    # Definite integral with bounds — 'dx' still stripped
    ("Find the integral of x^2 dx from 0 to 1", "definite_integral", "x^2"),
    # Limit: trailing 'as x approaches …' stripped from expr
    ("Find the limit of 1/x as x approaches infinity", "limit", "1/x"),
])
def test_parse_operation_strips_trailing_differentials(question, expected_operation, expected_expr):
    """parse_operation must strip trailing differential notation so SymPy
    receives a parseable expression."""
    operation, expr, _ = parse_operation(question)
    assert operation == expected_operation, f"operation mismatch: {operation!r}"
    assert expr == expected_expr, f"expr mismatch: {expr!r}"


@pytest.mark.parametrize("question,boxed,verdict", [
    # Integral of x^2 = x^3/3 (no 'C' since SymPy returns bare antiderivative)
    ("Find the integral of x^2 dx", r"\boxed{x^3/3}", True),
    # Integral of sin(x) = -cos(x)
    ("Find the integral of sin(x) dx", r"\boxed{-cos(x)}", True),
    # Wrong integral answer
    ("Find the integral of x^2 dx", r"\boxed{x^2}", False),
])
def test_integral_questions_now_verifiable(question, boxed, verdict):
    """Integral questions with trailing 'dx' in the phrasing must now
    return a definite verdict instead of a parse error."""
    correct, sympy_result, diagnostic = verify_cal_math(question, boxed)
    assert correct is verdict, (
        f"Expected verdict={verdict!r} but got correct={correct!r}. "
        f"sympy_result={sympy_result!r}, diagnostic={diagnostic!r}"
    )


@pytest.mark.parametrize("raw_response,expected_extracted", [
    # Plain boxed answer
    (r"\boxed{2*x}", "2*x"),
    # Equation with variable assignment (y = ...)
    (r"\boxed{y = 2*x}", "2*x"),
    # Function notation (f'(x) = ...)
    (r"\boxed{f'(x) = 2*x}", "2*x"),
    (r"\boxed{f(x) = 2*x}", "2*x"),
    # Leibniz derivative notation (\frac{dy}{dx} = ...)
    (r"\boxed{\frac{dy}{dx} = 2*x}", "2*x"),
    (r"\boxed{dy/dx = 2*x}", "2*x"),
    # Trailing punctuation inside the box
    (r"\boxed{2*x.}", "2*x"),
    (r"\boxed{2*x,}", "2*x"),
    # Math delimiters inside the box ($...$)
    (r"\boxed{$2*x$}", "2*x"),
])
def test_extract_boxed_answer_normalizes_equations_and_delimiters(raw_response, expected_extracted):
    """extract_boxed_answer must extract the substantive mathematical expression,
    stripping equation assignment prefixes, inner delimiters, and punctuation."""
    assert extract_boxed_answer(raw_response) == expected_extracted


@pytest.mark.parametrize("question,boxed,verdict", [
    # Derivative verified successfully even with 'y = ' or 'f\'(x) = ' prefix in box
    ("Find the derivative of x^2", r"\boxed{y = 2*x}", True),
    ("Find the derivative of x^2", r"\boxed{f'(x) = 2*x}", True),
    ("Find the derivative of x^2", r"\boxed{\frac{dy}{dx} = 2*x}", True),
    ("Find the derivative of x^2", r"\boxed{y = 3*x}", False),
])
def test_verify_cal_math_with_equation_prefixes(question, boxed, verdict):
    """Answers formatted with equation prefixes must be cleanly verified
    rather than causing parse errors."""
    correct, sympy_result, diagnostic = verify_cal_math(question, boxed)
    assert correct is verdict, (
        f"Expected verdict={verdict!r} but got correct={correct!r}. "
        f"sympy_result={sympy_result!r}, diagnostic={diagnostic!r}"
    )


# ---------------------------------------------------------------------------
# \cdot multiplication preprocessing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    # Basic \cdot replacement
    (r"2\cdot x",        "2*x"),
    # \cdot with surrounding spaces (common in hand-written LaTeX)
    (r"2 \cdot x",       "2*x"),
    # Multiple \cdot tokens in one expression
    (r"3\cdot x\cdot y", "3*x*y"),
    # \cdot between parenthesised sub-expressions
    (r"(x+1)\cdot(x-1)", "(x+1)*(x-1)"),
    # No \cdot — expression returned unchanged by this step
    ("2*x + 1",          "2*x + 1"),
    # \cdot adjacent to a trig function — note preprocess also converts \sin→sin
    (r"2\cdot\sin(x)",   "2*sin(x)"),
])
def test_preprocess_cdot_to_multiplication(raw, expected):
    r"""preprocess_math_expr must replace every \cdot token with '*',
    absorbing any surrounding whitespace."""
    assert preprocess_math_expr(raw) == expected


def test_verify_cal_math_with_cdot_in_answer():
    r"""An answer written as '2\cdot x' must verify correctly against the
    derivative of x^2, demonstrating end-to-end \cdot normalisation."""
    question = "Find the derivative of x^2"
    boxed = r"\boxed{2\cdot x}"
    correct, sympy_result, diagnostic = verify_cal_math(question, boxed)
    assert correct is True, (
        f"Expected True but got correct={correct!r}. "
        f"sympy_result={sympy_result!r}, diagnostic={diagnostic!r}"
    )


# ---------------------------------------------------------------------------
# Absolute value preprocessing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    # Standard pipe notation |x|
    ("|x|", "Abs(x)"),
    # Pipe notation with expression inside
    ("|x - 2|", "Abs(x - 2)"),
    # LaTeX \vert notation
    (r"\vert x \vert", "Abs(x)"),
    # LaTeX \left| ... \right|
    (r"\left| x \right|", "Abs(x)"),
    # LaTeX \left\vert ... \right\vert
    (r"\left\vert x - y \right\vert", "Abs(x - y)"),
    # Multiple absolute values in expression
    ("|x| + |y|", "Abs(x) + Abs(y)"),
    # Implicit multiplication with leading digit
    ("2|x|", "2*Abs(x)"),
    # Combined with \cdot
    (r"|x| \cdot 3", "Abs(x)*3"),
])
def test_preprocess_abs_notation(raw, expected):
    r"""preprocess_math_expr must normalize pipe and LaTeX vert absolute-value
    delimiters into SymPy-parseable Abs(...) function calls."""
    assert preprocess_math_expr(raw) == expected


def test_verify_cal_math_with_abs_in_question_and_answer():
    r"""Questions and boxed answers with absolute-value notation must verify
    correctly end-to-end rather than failing with parse errors."""
    question = "Simplify |x - 2|"
    boxed = r"\boxed{|x - 2|}"
    correct, sympy_result, diagnostic = verify_cal_math(question, boxed)
    assert correct is True, (
        f"Expected True but got correct={correct!r}. "
        f"sympy_result={sympy_result!r}, diagnostic={diagnostic!r}"
    )

    # And verify mismatch returns False
    wrong_boxed = r"\boxed{|x - 3|}"
    wrong_correct, _, _ = verify_cal_math(question, wrong_boxed)
    assert wrong_correct is False
