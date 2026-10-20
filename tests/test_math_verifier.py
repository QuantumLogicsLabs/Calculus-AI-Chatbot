import pytest

from aiService.services.math_verifier import verify_cal_math, _strip_differential, parse_operation


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
