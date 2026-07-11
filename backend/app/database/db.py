"""
CalcVoyager Backend - Database Layer
SQLite (aiosqlite) persistence for chat sessions, messages, feedback (CB-12),
and per-topic adaptive difficulty tracking (CB-18).
"""
import os
import logging
from typing import Optional, Any

import aiosqlite

logging.basicConfig(level=logging.INFO)

DB_PATH = os.path.join(os.path.dirname(__file__), "calcvoyager.db")

# ── Adaptive difficulty tuning (CB-18) ────────────────────────────────────────
DIFFICULTY_LEVELS = ("beginner", "intermediate", "advanced")

LIKE_DELTA = 2.0
DISLIKE_DELTA = -3.0
MASTERY_STEP = 4          # every N clean messages on a topic nudges the score up
MASTERY_DELTA = 1.0

LEVEL_THRESHOLDS = (
    (8.0, "advanced"),
    (3.0, "intermediate"),
)


def _score_to_level(score: float) -> str:
    for threshold, level in LEVEL_THRESHOLDS:
        if score >= threshold:
            return level
    return "beginner"


SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    session_id TEXT NOT NULL UNIQUE,
    title TEXT DEFAULT 'New Chat',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    message_type TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS message_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    feedback TEXT NOT NULL,
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE(message_id, user_id)
);

-- CB-18: Adaptive difficulty, tracked per user/topic
CREATE TABLE IF NOT EXISTS topic_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    topic TEXT NOT NULL,
    difficulty_level TEXT NOT NULL DEFAULT 'beginner',
    difficulty_score REAL NOT NULL DEFAULT 0,
    message_count INTEGER NOT NULL DEFAULT 0,
    like_count INTEGER NOT NULL DEFAULT 0,
    dislike_count INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE(user_id, topic)
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON chat_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_user ON chat_messages(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON chat_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_progress_user ON topic_progress(user_id);
"""

_initialized = False


async def init_db():
    """Create tables if they don't exist yet. Safe to call repeatedly."""
    global _initialized
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()
    _initialized = True
    logging.info(f"Database ready at {DB_PATH}")


async def _ensure_ready():
    if not _initialized:
        await init_db()


def _row_to_dict(cursor, row):
    if row is None:
        return None
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


# ── Generic helpers used across routes ────────────────────────────────────────

async def fetchone(query: str, params: tuple = ()) -> Optional[dict]:
    await _ensure_ready()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(query, params)
        row = await cursor.fetchone()
        result = _row_to_dict(cursor, row)
        await cursor.close()
        return result


async def fetchall(query: str, params: tuple = ()) -> list:
    await _ensure_ready()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        results = [_row_to_dict(cursor, row) for row in rows]
        await cursor.close()
        return results


async def execute(query: str, params: tuple = ()) -> int:
    """
    Runs an INSERT/UPDATE/DELETE and returns the row id
    (lastrowid) for INSERTs, or the row count otherwise.
    """
    await _ensure_ready()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(query, params)
        await db.commit()
        row_id = cursor.lastrowid
        await cursor.close()
        return row_id


async def scalar(query: str, params: tuple = ()) -> Any:
    await _ensure_ready()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(query, params)
        row = await cursor.fetchone()
        await cursor.close()
        return row[0] if row else None


# ── CB-12: message feedback ────────────────────────────────────────────────────

async def upsert_feedback(message_id: int, user_id: int, session_id: str, feedback: str) -> None:
    await _ensure_ready()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO message_feedback (message_id, user_id, session_id, feedback, updated_at)
            VALUES (?, ?, ?, ?, strftime('%s','now'))
            ON CONFLICT(message_id, user_id) DO UPDATE SET
                feedback = excluded.feedback,
                updated_at = strftime('%s','now')
            """,
            (message_id, user_id, session_id, feedback)
        )
        await db.commit()


async def get_feedback_for_message(message_id: int, user_id: int) -> Optional[dict]:
    return await fetchone(
        "SELECT message_id, feedback, created_at, updated_at "
        "FROM message_feedback WHERE message_id = ? AND user_id = ?",
        (message_id, user_id)
    )


# ── CB-18: adaptive difficulty ────────────────────────────────────────────────

async def _get_or_create_topic_row(db: aiosqlite.Connection, user_id: int, topic: str) -> dict:
    cursor = await db.execute(
        "SELECT * FROM topic_progress WHERE user_id = ? AND topic = ?",
        (user_id, topic)
    )
    row = await cursor.fetchone()
    result = _row_to_dict(cursor, row)
    await cursor.close()

    if result is None:
        await db.execute(
            "INSERT INTO topic_progress (user_id, topic, difficulty_level, difficulty_score) "
            "VALUES (?, ?, 'beginner', 0)",
            (user_id, topic)
        )
        await db.commit()
        cursor = await db.execute(
            "SELECT * FROM topic_progress WHERE user_id = ? AND topic = ?",
            (user_id, topic)
        )
        row = await cursor.fetchone()
        result = _row_to_dict(cursor, row)
        await cursor.close()

    return result


async def get_topic_progress(user_id: int, topic: str) -> dict:
    """Returns (creating if needed) the progress row for a user/topic pair."""
    await _ensure_ready()
    topic = (topic or "general").strip().lower()
    async with aiosqlite.connect(DB_PATH) as db:
        return await _get_or_create_topic_row(db, user_id, topic)


async def get_all_topic_progress(user_id: int) -> list:
    """Returns progress across every topic the student has touched (CB-18 dashboard)."""
    return await fetchall(
        "SELECT topic, difficulty_level, difficulty_score, message_count, "
        "like_count, dislike_count, updated_at "
        "FROM topic_progress WHERE user_id = ? ORDER BY updated_at DESC",
        (user_id,)
    )


async def record_topic_message(user_id: int, topic: str) -> dict:
    """
    Called once per assistant turn on a topic. Slowly nudges the difficulty
    score (and therefore level) upward every MASTERY_STEP clean messages,
    modelling gradual mastery when nothing has gone wrong.
    """
    await _ensure_ready()
    topic = (topic or "general").strip().lower()

    async with aiosqlite.connect(DB_PATH) as db:
        current = await _get_or_create_topic_row(db, user_id, topic)

        new_count = current["message_count"] + 1
        new_score = current["difficulty_score"]
        if new_count % MASTERY_STEP == 0:
            new_score += MASTERY_DELTA
        new_level = _score_to_level(new_score)

        await db.execute(
            "UPDATE topic_progress SET message_count = ?, difficulty_score = ?, "
            "difficulty_level = ?, updated_at = strftime('%s','now') "
            "WHERE user_id = ? AND topic = ?",
            (new_count, new_score, new_level, user_id, topic)
        )
        await db.commit()

        return {
            "topic": topic,
            "difficulty_level": new_level,
            "difficulty_score": new_score,
            "message_count": new_count,
        }


async def record_topic_feedback(user_id: int, topic: str, feedback: str) -> dict:
    """
    Called when a student rates a message (CB-12 hook into CB-18).
    Likes push the difficulty up, dislikes pull it back down — the
    core adaptive signal for "was this pitched at the right level?".
    """
    await _ensure_ready()
    topic = (topic or "general").strip().lower()

    async with aiosqlite.connect(DB_PATH) as db:
        current = await _get_or_create_topic_row(db, user_id, topic)

        like_count = current["like_count"]
        dislike_count = current["dislike_count"]
        score = current["difficulty_score"]

        if feedback == "like":
            like_count += 1
            score += LIKE_DELTA
        elif feedback == "dislike":
            dislike_count += 1
            score += DISLIKE_DELTA

        score = max(0.0, score)
        level = _score_to_level(score)

        await db.execute(
            "UPDATE topic_progress SET like_count = ?, dislike_count = ?, "
            "difficulty_score = ?, difficulty_level = ?, updated_at = strftime('%s','now') "
            "WHERE user_id = ? AND topic = ?",
            (like_count, dislike_count, score, level, user_id, topic)
        )
        await db.commit()

        return {
            "topic": topic,
            "difficulty_level": level,
            "difficulty_score": score,
            "like_count": like_count,
            "dislike_count": dislike_count,
        }