import pytest

from aiService.services.math_verifier import verify_cal_math


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
