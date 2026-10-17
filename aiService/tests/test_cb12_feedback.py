"""Exercise the real backend feedback route and SQLite helpers in isolation.

Authentication is patched per test; these tests do not certify the placeholder
Bearer-token authentication. Each test gets a temporary on-disk SQLite database
because the production helpers open a new connection for every query.
"""

import sqlite3
from contextlib import ExitStack

import pytest
from starlette.testclient import TestClient

from backend.app.main import app
from backend.app.routes import chat as chat_module
from backend.app.database import db as db_module

USER_ID = 1
SESSION_ID = "test-session-uuid"
_test_conn = None
_clients = None


def _get_test_connection():
    return _test_conn


def _seed_db(user_id=USER_ID, session_id=SESSION_ID):
    conn = _get_test_connection()
    conn.execute(
        "INSERT INTO chat_sessions (user_id, session_id, title) VALUES (?, ?, ?)",
        (user_id, session_id, "Test Session"),
    )
    cursor = conn.execute(
        "INSERT INTO chat_messages (user_id, session_id, message_type, content) "
        "VALUES (?, ?, 'assistant', 'Here is your calculus answer.')",
        (user_id, session_id),
    )
    conn.commit()
    return cursor.lastrowid


def _make_app(user_id=None):
    chat_module.require_user = lambda request: user_id
    return _clients.enter_context(TestClient(app))


@pytest.fixture(autouse=True)
def fresh_db(isolated_db, monkeypatch):
    global _test_conn, _clients
    # Register the original auth function for restoration after direct per-test overrides.
    monkeypatch.setattr(chat_module, "require_user", chat_module.require_user)
    with sqlite3.connect(db_module.DB_PATH) as conn, ExitStack() as clients:
        conn.row_factory = sqlite3.Row
        _test_conn, _clients = conn, clients
        yield
    _test_conn = _clients = None


class TestFeedbackSuccess:
    """Happy-path cases — valid votes from authenticated users."""

    def test_like_returns_200(self):
        message_id = _seed_db(USER_ID, SESSION_ID)
        client = _make_app(user_id=USER_ID)

        resp = client.post("/api/chat/feedback", json={
            "message_id": message_id,
            "session_id": SESSION_ID,
            "feedback":   "like"
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["feedback"] == "like"
        assert data["data"]["message_id"] == message_id

    def test_dislike_returns_200(self):
        message_id = _seed_db(USER_ID, SESSION_ID)
        client = _make_app(user_id=USER_ID)

        resp = client.post("/api/chat/feedback", json={
            "message_id": message_id,
            "session_id": SESSION_ID,
            "feedback":   "dislike"
        })

        assert resp.status_code == 200
        assert resp.json()["data"]["feedback"] == "dislike"

    def test_feedback_row_persisted_in_db(self):
        """After a like, a real row must exist in message_feedback."""
        message_id = _seed_db(USER_ID, SESSION_ID)
        client = _make_app(user_id=USER_ID)

        client.post("/api/chat/feedback", json={
            "message_id": message_id,
            "session_id": SESSION_ID,
            "feedback":   "like"
        })

        conn = _get_test_connection()
        row = conn.execute(
            "SELECT feedback FROM message_feedback WHERE message_id = ? AND user_id = ?",
            (message_id, USER_ID)
        ).fetchone()

        assert row is not None, "No row found in message_feedback"
        assert row["feedback"] == "like"


class TestUpsertBehaviour:
    """Re-voting must UPDATE the existing row, not INSERT a duplicate."""

    def test_revote_changes_value(self):
        message_id = _seed_db(USER_ID, SESSION_ID)
        client = _make_app(user_id=USER_ID)

        # First vote: like
        client.post("/api/chat/feedback", json={
            "message_id": message_id,
            "session_id": SESSION_ID,
            "feedback":   "like"
        })

        # Second vote: dislike (change of mind)
        resp = client.post("/api/chat/feedback", json={
            "message_id": message_id,
            "session_id": SESSION_ID,
            "feedback":   "dislike"
        })

        assert resp.status_code == 200
        assert resp.json()["data"]["feedback"] == "dislike"

    def test_revote_does_not_duplicate_row(self):
        """Only one row per (message_id, user_id) should ever exist."""
        message_id = _seed_db(USER_ID, SESSION_ID)
        client = _make_app(user_id=USER_ID)

        client.post("/api/chat/feedback", json={
            "message_id": message_id, "session_id": SESSION_ID, "feedback": "like"
        })
        client.post("/api/chat/feedback", json={
            "message_id": message_id, "session_id": SESSION_ID, "feedback": "dislike"
        })

        conn = _get_test_connection()
        count = conn.execute(
            "SELECT COUNT(*) FROM message_feedback WHERE message_id = ? AND user_id = ?",
            (message_id, USER_ID)
        ).fetchone()[0]

        assert count == 1, f"Expected 1 row, found {count} (upsert created duplicates)"


class TestValidation:
    """Bad input must be rejected with 400 before touching the DB."""

    def test_missing_message_id(self):
        _seed_db(USER_ID, SESSION_ID)
        client = _make_app(user_id=USER_ID)

        resp = client.post("/api/chat/feedback", json={
            "session_id": SESSION_ID,
            "feedback":   "like"
        })
        assert resp.status_code == 400

    def test_missing_session_id(self):
        message_id = _seed_db(USER_ID, SESSION_ID)
        client = _make_app(user_id=USER_ID)

        resp = client.post("/api/chat/feedback", json={
            "message_id": message_id,
            "feedback":   "like"
        })
        assert resp.status_code == 400

    def test_missing_feedback(self):
        message_id = _seed_db(USER_ID, SESSION_ID)
        client = _make_app(user_id=USER_ID)

        resp = client.post("/api/chat/feedback", json={
            "message_id": message_id,
            "session_id": SESSION_ID,
        })
        assert resp.status_code == 400

    def test_invalid_feedback_value(self):
        """Only 'like' and 'dislike' are valid — anything else is 400."""
        message_id = _seed_db(USER_ID, SESSION_ID)
        client = _make_app(user_id=USER_ID)

        resp = client.post("/api/chat/feedback", json={
            "message_id": message_id,
            "session_id": SESSION_ID,
            "feedback":   "meh"
        })
        assert resp.status_code == 400
        assert "like" in resp.json()["detail"] or "dislike" in resp.json()["detail"]

    def test_non_integer_message_id(self):
        _seed_db(USER_ID, SESSION_ID)
        client = _make_app(user_id=USER_ID)

        resp = client.post("/api/chat/feedback", json={
            "message_id": "abc",
            "session_id": SESSION_ID,
            "feedback":   "like"
        })
        assert resp.status_code == 400

    def test_empty_body(self):
        _seed_db(USER_ID, SESSION_ID)
        client = _make_app(user_id=USER_ID)

        resp = client.post("/api/chat/feedback", json={})
        assert resp.status_code == 400


class TestAuth:
    """Unauthenticated (guest) requests must be rejected with 401."""

    def test_guest_gets_401(self):
        message_id = _seed_db(USER_ID, SESSION_ID)
        client = _make_app(user_id=None)  # guest

        resp = client.post("/api/chat/feedback", json={
            "message_id": message_id,
            "session_id": SESSION_ID,
            "feedback":   "like"
        })
        assert resp.status_code == 401

    def test_guest_leaves_no_db_row(self):
        """A rejected guest request must not write anything to the DB."""
        message_id = _seed_db(USER_ID, SESSION_ID)
        client = _make_app(user_id=None)

        client.post("/api/chat/feedback", json={
            "message_id": message_id,
            "session_id": SESSION_ID,
            "feedback":   "like"
        })

        conn = _get_test_connection()
        count = conn.execute(
            "SELECT COUNT(*) FROM message_feedback"
        ).fetchone()[0]

        assert count == 0, "Guest request wrote a row — auth guard failed"


class TestOwnership:
    """A user must not be able to vote on another user's messages."""

    def test_wrong_user_gets_404(self):
        """
        Message belongs to USER_ID=1.
        Request authenticated as USER_ID=2.
        Should return 404 — message not found in their session.
        """
        message_id = _seed_db(user_id=1, session_id=SESSION_ID)

        client = _make_app(user_id=2)  # different user

        resp = client.post("/api/chat/feedback", json={
            "message_id": message_id,
            "session_id": SESSION_ID,
            "feedback":   "like"
        })
        assert resp.status_code == 404

    def test_wrong_session_gets_404(self):
        """
        Valid user, valid message_id, but wrong session_id in the body.
        Should return 404.
        """
        message_id = _seed_db(USER_ID, SESSION_ID)
        client = _make_app(user_id=USER_ID)

        resp = client.post("/api/chat/feedback", json={
            "message_id": message_id,
            "session_id": "completely-wrong-session-id",
            "feedback":   "like"
        })
        assert resp.status_code == 404

    def test_nonexistent_message_gets_404(self):
        _seed_db(USER_ID, SESSION_ID)
        client = _make_app(user_id=USER_ID)

        resp = client.post("/api/chat/feedback", json={
            "message_id": 99999,   # doesn't exist
            "session_id": SESSION_ID,
            "feedback":   "like"
        })
        assert resp.status_code == 404
