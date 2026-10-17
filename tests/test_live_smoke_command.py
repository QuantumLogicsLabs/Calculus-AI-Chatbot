"""Test the live-verification gate without making a real model call."""
import httpx
import pytest
from scripts.verify_live_chat import verify


def stub(mode="live", source="primary", bad_answer=False, status=200):
    def handle(request):
        assert request.url.path == "/api/chat/"
        reply = r"The derivative is \boxed{3*x**2}" if b"x**3" in request.content else r"The derivative is \boxed{cos(x)}"
        if bad_answer:
            reply = r"The derivative is \boxed{0}"
        return httpx.Response(status, json={"reply": reply, "mode": mode, "source": source})
    return httpx.Client(transport=httpx.MockTransport(handle))


def test_live_smoke_accepts_verified_distinct_results():
    with stub() as client:
        result = verify(client, "http://testserver")
    assert len(result) == 2 and all(item["math_verified"] for item in result)


@pytest.mark.parametrize("options", [
    {"mode": "mock"}, {"source": "cache"}, {"source": None},
    {"bad_answer": True}, {"status": 503},
])
def test_live_smoke_rejects_mock_cached_wrong_or_failed_answers(options):
    with stub(**options) as client, pytest.raises(RuntimeError):
        verify(client, "http://testserver")
