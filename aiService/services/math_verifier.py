"""
CB-16: Symbolic Math Verification Layer
Uses SymPy to independently verify Cal's mathematical answers and
guard against calculation hallucinations.
"""

import re
import sympy as sp
from typing import Tuple, Optional, List

x, y, z, t, u, v = sp.symbols('x y z t u v', real=True)
COMMON_SYMBOLS = {'x': x, 'y': y, 'z': z, 't': t, 'u': u, 'v': v}


def preprocess_math_expr(expr: str) -> str:
    """
    Normalize common human/LLM math notation into SymPy-parseable syntax:
    - '^' -> '**'
    - implicit multiplication: '2x' -> '2*x', 'x2' -> 'x*2', ')(' -> ')*('
    """
    if not expr:
        return expr
    expr = expr.replace('^', '**')
    expr = re.sub(r'(\d)([a-zA-Z(])', r'\1*\2', expr)
    expr = re.sub(r'([a-zA-Z])(\d)', r'\1*\2', expr)
    expr = re.sub(r'\)(\()', r')*(', expr)
    return expr


def extract_boxed_answer(cal_response: str) -> Optional[str]:
    """Extract the content inside \\boxed{...}. Handles one level of
    nested braces (e.g. \\boxed{\\frac{1}{2}})."""
    match = re.search(r'\\boxed\{((?:[^{}]|\{[^{}]*\})*)\}', cal_response)
    if match:
        return match.group(1).strip()
    return None


def detect_variables_in_question(question: str) -> list:
    """Detect which variables are mentioned in the question."""
    variables = []
    for var in ['x', 'y', 'z', 't', 'u', 'v']:
        if re.search(rf'\b{var}\b', question):
            variables.append(var)
    return variables or ['x']


def _extract_limit_point(question_lower: str) -> str:
    """Return a SymPy-parseable limit point as a string (default 'oo')."""
    if re.search(r'infinity|→\s*∞|-> ?oo|approaches infinity', question_lower):
        return 'oo'
    if re.search(r'negative infinity|-∞|-> ?-oo', question_lower):
        return '-oo'
    match = re.search(
        r'(?:approaches|approach|as\s+[a-z]\s*(?:->|→)|tends to)\s*(-?\d+(?:\.\d+)?)',
        question_lower
    )
    if match:
        return match.group(1)
    return 'oo'


def _extract_integral_bounds(question_lower: str):
    """Return (lower, upper) bounds as strings, or None for indefinite."""
    match = re.search(
        r'(?:from|between)\s+(-?\d+(?:\.\d+)?)\s+(?:to|and)\s+(-?\d+(?:\.\d+)?)',
        question_lower
    )
    if match:
        return match.group(1), match.group(2)
    return None


def parse_operation(question: str) -> Tuple[str, str, Optional[str]]:
    """Detect the math operation and extract the expression.

    Returns (operation, expression_str, extra) where `extra` is the
    diff/integration variable for most ops, or a limit point / bounds
    packed as a string for limit / definite integral ops (see
    sympy_solve for how each is consumed).
    """
    question_lower = question.lower()

    if 'gradient' in question_lower:
        match = re.search(r'gradient\s+of\s+([^.?]+?)(?:\s+at\b|$)', question_lower)
        expr = match.group(1).strip() if match else 'x**2 + y**2'
        return 'gradient', expr, None

    if 'second' in question_lower and ('derivative' in question_lower or 'differentiate' in question_lower):
        var_match = re.search(r'(?:with respect to|w\.?r\.?t\.?)\s*([a-z])', question_lower)
        diff_var = var_match.group(1) if var_match else 'x'
        match = re.search(r'(?:derivative|differentiate)\s+(?:of\s+)?([^.?]+?)(?:\s+w\.?r\.?t\.|$)', question_lower)
        expr = match.group(1).strip() if match else 'x**2'
        return 'second_derivative', expr, diff_var

    if 'partial' in question_lower and ('derivative' in question_lower or 'differentiate' in question_lower):
        var_match = re.search(r'(?:with respect to|w\.?r\.?t\.?)\s*([a-z])', question_lower)
        diff_var = var_match.group(1) if var_match else 'x'
        match = re.search(r'(?:partial\s+)?(?:derivative|differentiate)\s+(?:of\s+)?([^.?]+?)(?:\s+w\.?r\.?t\.|$)', question_lower)
        expr = match.group(1).strip() if match else 'x*y'
        return 'partial_derivative', expr, diff_var

    if 'derivative' in question_lower or 'differentiate' in question_lower:
        var_match = re.search(r'd/d([a-z])', question_lower)
        diff_var = var_match.group(1) if var_match else 'x'
        match = re.search(r'(?:derivative|differentiate)\s+(?:of\s+)?([^.?]+?)(?:\s+w\.?r\.?t\.|$)', question_lower)
        expr = match.group(1).strip() if match else 'x**2'
        return 'derivative', expr, diff_var

    if 'integral' in question_lower or 'integrate' in question_lower:
        match = re.search(r'(?:integral|integrate)\s+(?:of\s+)?([^.?]+)', question_lower)
        expr = match.group(1).strip() if match else 'x**2'
        bounds = _extract_integral_bounds(question_lower)
        if bounds:
            return 'definite_integral', expr, f"{bounds[0]},{bounds[1]}"
        return 'integral', expr, 'x'

    if 'limit' in question_lower:
        match = re.search(r'limit\s+(?:of\s+)?([^.?]+)', question_lower)
        expr = match.group(1).strip() if match else '1/x'
        point = _extract_limit_point(question_lower)
        return 'limit', expr, point

    return 'simplify', question_lower.strip(), None


def sympy_solve(operation: str, expression_str: str, diff_var: Optional[str] = None) -> Optional[str]:
    """Use SymPy to independently solve the math problem."""
    try:
        expr = sp.sympify(preprocess_math_expr(expression_str), locals=COMMON_SYMBOLS)

        if operation == 'derivative' and diff_var:
            var = COMMON_SYMBOLS.get(diff_var, sp.Symbol(diff_var))
            result = sp.diff(expr, var)

        elif operation == 'second_derivative' and diff_var:
            var = COMMON_SYMBOLS.get(diff_var, sp.Symbol(diff_var))
            result = sp.diff(expr, var, 2)

        elif operation == 'partial_derivative' and diff_var:
            var = COMMON_SYMBOLS.get(diff_var, sp.Symbol(diff_var))
            result = sp.diff(expr, var)

        elif operation == 'gradient':
            free_vars = sorted(expr.free_symbols, key=lambda s: s.name)
            if not free_vars:
                free_vars = [x]
            result = sp.Matrix([sp.diff(expr, v) for v in free_vars])

        elif operation == 'integral':
            var = COMMON_SYMBOLS.get(diff_var, sp.Symbol(diff_var)) if diff_var else x
            result = sp.integrate(expr, var)

        elif operation == 'definite_integral' and diff_var:
            lower_str, upper_str = diff_var.split(',')
            lower = sp.sympify(lower_str)
            upper = sp.sympify(upper_str)
            result = sp.integrate(expr, (x, lower, upper))

        elif operation == 'limit':
            point = sp.sympify(diff_var) if diff_var else sp.oo
            result = sp.limit(expr, x, point)

        else:
            result = sp.simplify(expr)

        return str(result)
    except Exception:
        return None


def verify_cal_math(question_text: str, cal_response: str) -> Tuple[Optional[bool], Optional[str], Optional[str]]:
    """
    Main verification function. Returns (is_correct, sympy_result, error).

    is_correct:
        True  -> Cal's boxed answer matches the independent SymPy result
        False -> Cal's boxed answer does NOT match (likely hallucination)
        None  -> could not verify (unsupported operation / unparseable
                 expression) — treat as "no verdict", not a pass
    """
    cal_answer = extract_boxed_answer(cal_response)
    if not cal_answer:
        return None, None, "No boxed answer found."

    try:
        operation, expr, diff_var = parse_operation(question_text)
    except Exception:
        return None, None, "Could not parse question."

    try:
        sympy_result = sympy_solve(operation, expr, diff_var)
    except Exception:
        sympy_result = None

    if sympy_result is None:
        return None, None, f"SymPy could not parse or solve: {expr}"

    try:
        cal_expr = sp.sympify(preprocess_math_expr(cal_answer), locals=COMMON_SYMBOLS)
        sympy_expr = sp.sympify(sympy_result, locals=COMMON_SYMBOLS)
        diff = sp.simplify(cal_expr - sympy_expr)
        is_correct = diff == 0
        return is_correct, sympy_result, None
    except Exception:
        return False, sympy_result, "Could not parse Cal's boxed answer for comparison."