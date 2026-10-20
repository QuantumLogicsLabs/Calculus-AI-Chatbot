import pytest

from aiService.services.math_verifier import verify_cal_math, preprocess_math_expr


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
    # \frac{a}{b} -> (a)/(b)
    (r"\frac{1}{x}", "(1)/(x)"),
    (r"\frac{x^2}{2}", "(x**2)/(2)"),
    # \frac with nested braces in numerator or denominator
    (r"\frac{x^2+1}{x-1}", "(x**2+1)/(x-1)"),
    # \sqrt{x} -> sqrt(x)
    (r"\sqrt{x}", "sqrt(x)"),
    (r"\sqrt{x^2+1}", "sqrt(x**2+1)"),
    # Expressions with no LaTeX structure are returned unchanged (aside from ^->**)
    ("x**2 + 1", "x**2 + 1"),
    # Ensure trig functions still work after frac conversion
    (r"\sin(x)", "sin(x)"),
])
def test_preprocess_math_expr_latex_conversions(raw, expected):
    """preprocess_math_expr must convert \\frac and \\sqrt to SymPy-compatible
    notation while preserving all other existing transformations."""
    assert preprocess_math_expr(raw) == expected


@pytest.mark.parametrize("question,boxed,verdict", [
    # Derivative of ln(x) = 1/x expressed as \frac{1}{x}
    ("Find the derivative of ln(x)", r"\boxed{\frac{1}{x}}", True),
    # Derivative of x^2 = 2x (not a fraction, baseline)
    ("Find the derivative of x^2", r"\boxed{2*x}", True),
    # Wrong fraction answer
    ("Find the derivative of ln(x)", r"\boxed{\frac{1}{x^2}}", False),
    # Square root answer: derivative of sqrt(x) = 1/(2*sqrt(x))
    ("Find the derivative of sqrt(x)", r"\boxed{\frac{1}{2*sqrt(x)}}", True),
])
def test_frac_answers_now_verifiable(question, boxed, verdict):
    """Answers written as \\boxed{\\frac{...}{...}} must now yield a concrete
    True/False verdict instead of a parse error."""
    correct, sympy_result, diagnostic = verify_cal_math(question, boxed)
    assert correct is verdict, (
        f"Expected verdict={verdict!r} but got correct={correct!r}. "
        f"sympy_result={sympy_result!r}, diagnostic={diagnostic!r}"
    )
