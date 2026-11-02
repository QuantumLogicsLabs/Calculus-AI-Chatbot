"""The chatbot accepts the main backend's login tokens and nothing else."""
from datetime import datetime, timedelta, timezone

import jwt
from starlette.requests import Request

from backend.app.auth.auth_utils import require_user

SECRET = "test-shared-secret-at-least-32-bytes-long"


def _request(token=None):
    headers = []
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    return Request({"type": "http", "method": "POST", "path": "/api/chat/", "headers": headers})


def _token(user_id, secret=SECRET, minutes=10):
    payload = {"sub": str(user_id), "exp": datetime.now(timezone.utc) + timedelta(minutes=minutes)}
    return jwt.encode(payload, secret, algorithm="HS256")


def test_valid_main_backend_token_returns_user_id(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", SECRET)
    monkeypatch.delenv("CALCVOYAGER_PREVIEW", raising=False)
    assert require_user(_request(_token(42))) == 42


def test_no_token_is_guest(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", SECRET)
    monkeypatch.delenv("CALCVOYAGER_PREVIEW", raising=False)
    assert require_user(_request()) is None


def test_fake_token_is_guest(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", SECRET)
    monkeypatch.delenv("CALCVOYAGER_PREVIEW", raising=False)
    assert require_user(_request("pretend-login")) is None


def test_token_signed_with_other_secret_is_guest(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", SECRET)
    monkeypatch.delenv("CALCVOYAGER_PREVIEW", raising=False)
    assert require_user(_request(_token(42, secret="someone-elses-secret-also-32-bytes-long"))) is None


def test_expired_token_is_guest(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", SECRET)
    monkeypatch.delenv("CALCVOYAGER_PREVIEW", raising=False)
    assert require_user(_request(_token(42, minutes=-5))) is None


def test_preview_mode_is_always_guest(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", SECRET)
    monkeypatch.setenv("CALCVOYAGER_PREVIEW", "true")
    assert require_user(_request(_token(42))) is None
