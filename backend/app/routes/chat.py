# routers/chat.py - Complete chat implementation for Starlette
import asyncio
import json
import re
import uuid
import httpx
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, AsyncGenerator
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

# from auth_utils import require_user
from backend.app.auth.auth_utils import require_user
# from db import fetchone, fetchall, execute, scalar
from backend.app.database.db import (
    fetchone, fetchall, execute, scalar,
    upsert_feedback, get_feedback_for_message,  # CB-12
    get_topic_progress, get_all_topic_progress,  # CB-18
    record_topic_message, record_topic_feedback,  # CB-18
)

# Configuration for aiService
AI_SERVICE_URL = "http://127.0.0.1:8001"  # aiService chatbot.py runs on port 8001

# ── T5: SSE Streaming Tunables ────────────────────────────────────────────────
# FLUSH_INTERVAL bounds how long a token can sit before being sent to the
# client — lower = snappier "typing" feel, higher = fewer frames/less overhead.
FLUSH_INTERVAL = 0.03          # 30ms
HEARTBEAT_INTERVAL = 15.0      # keep-alive comment if nothing to send
STREAM_QUEUE_MAX = 1000        # backpressure guard


def sse_format(data: str, event: Optional[str] = None) -> str:
    """Correctly frame a payload as an SSE event (handles multi-line data)."""
    lines = data.split("\n")
    payload = "\n".join(f"data: {line}" for line in lines)
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}{payload}\n\n"

# ── CB-11/CB-14: Rate Limiting ───────────────────────────────────────────────

class RateLimiter:
    """
    In-memory rate limiter supporting both authenticated users and guests.
    - Authenticated users: 50 messages/day (keyed by user_id)
    - Guests: 10 messages/session (keyed by session identifier from request)
    """
    def __init__(self):
        self.limits = {}  # key -> (count, reset_time)
        self.user_day_limit = 50
        self.guest_session_limit = 10
        self.day_seconds = 86400  # 24 hours
        self.session_seconds = 3600  # 1 hour for guests

    def _get_guest_key(self, request: Request) -> str:
        """Generate a unique key for guest users (IP-based or random session)"""
        forwarded = request.headers.get("x-forwarded-for")
        ip = forwarded.split(",")[0].strip() if forwarded else request.client.host if request.client else "unknown"
        return f"guest_{ip}"

    async def check_limit(self, request: Request, user_id: Optional[int]) -> Optional[Dict[str, Any]]:
        """
        Check if the request is within rate limits.
        Returns None if allowed, or a dict with error details if rate-limited.
        """
        now = time.time()

        if user_id:
            # Authenticated user: 50/day
            key = f"user_{user_id}"
            limit = self.user_day_limit
            window = self.day_seconds
        else:
            # Guest: 10/session (1 hour)
            key = self._get_guest_key(request)
            limit = self.guest_session_limit
            window = self.session_seconds

        if key not in self.limits:
            self.limits[key] = (1, now + window)
            return None

        count, reset_time = self.limits[key]

        if now > reset_time:
            # Window expired, reset
            self.limits[key] = (1, now + window)
            return None

        if count >= limit:
            # Rate limit exceeded
            retry_after = int(reset_time - now)
            user_type = "authenticated" if user_id else "guest"
            return {
                "detail": f"Rate limit exceeded ({limit} messages per {'day' if user_id else 'hour'} for {user_type} users). Please try again later.",
                "retry_after": retry_after,
            }

        # Increment and allow
        self.limits[key] = (count + 1, reset_time)
        return None

_rate_limiter = RateLimiter()

# ── Helper Functions ──────────────────────────────────────────────────────────

async def get_user_id(request: Request):
    """Get user_id from request or return 401 response"""
    user_id = require_user(request)
    if user_id is None:
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    return user_id

async def validate_session(user_id: int, session_id: str) -> Optional[Dict[str, Any]]:
    """Validate session exists and belongs to user"""
    return await fetchone(
        "SELECT id, user_id, session_id, title, is_active, created_at, updated_at "
        "FROM chat_sessions WHERE user_id = ? AND session_id = ? AND is_active = 1",
        (user_id, session_id)
    )

def json_response(data, status=200):
    """Helper for consistent JSON responses"""
    return JSONResponse(data, status_code=status)


def _fmt_ts(ts) -> str:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return ""


def build_study_sheet(session: Dict[str, Any], messages: list) -> str:
    """
    CB-19 — Turns a session's raw message log into a revision-ready
    Markdown study sheet: a "key formulas" digest pulled from every
    display-LaTeX block ($$...$$) the tutor produced, followed by the
    full Q&A trail in chronological order.
    """
    title = session.get("title") or "Study Session"
    created = _fmt_ts(session.get("created_at"))
    updated = _fmt_ts(session.get("updated_at"))

    lines = [
        f"# {title}",
        "",
        f"_Exported from CalcVoyager · started {created} · last active {updated}_",
        "",
        "---",
        "",
    ]

    # ── Key formulas & definitions digest ──────────────────────────────────
    formula_pattern = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
    seen = set()
    formulas = []
    for msg in messages:
        if msg.get("message_type") != "assistant":
            continue
        for match in formula_pattern.findall(msg.get("content", "")):
            cleaned = match.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                formulas.append(cleaned)

    if formulas:
        lines.append("## 📐 Key Formulas & Results")
        lines.append("")
        for f in formulas:
            lines.append(f"- $${f}$$")
        lines.append("")
        lines.append("---")
        lines.append("")

    # ── Full conversation trail ─────────────────────────────────────────────
    lines.append("## 💬 Full Conversation")
    lines.append("")

    for msg in messages:
        role = msg.get("message_type")
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            lines.append(f"**Q:** {content}")
        elif role == "assistant":
            lines.append(f"**Cal:** {content}")
        else:
            continue
        lines.append("")

    return "\n".join(lines)


async def _get_or_create_active_session(user_id: int, user_message: str) -> str:
    """
    Shared by chat_endpoint and chat_stream_endpoint: fetch the user's
    active session, or create one seeded with a title from the first
    message, exactly like chat_endpoint already does.
    """
    active_session = await fetchone(
        "SELECT session_id FROM chat_sessions "
        "WHERE user_id = ? AND is_active = 1 "
        "ORDER BY updated_at DESC LIMIT 1",
        (user_id,)
    )
    if active_session:
        return active_session['session_id']

    session_id = str(uuid.uuid4())
    title = user_message[:50] + ('...' if len(user_message) > 50 else '')
    await execute(
        "INSERT INTO chat_sessions (user_id, session_id, title, updated_at) "
        "VALUES (?, ?, ?, strftime('%s','now'))",
        (user_id, session_id, title)
    )
    return session_id


async def _persist_turn(
    user_id: int,
    user_message: str,
    reply: str,
    suggestions: list,
    topic_key: str,
    page_url: str,
) -> Dict[str, Any]:
    """
    Shared persistence logic: saves the user + assistant messages, bumps
    session updated_at, and updates the CB-18 adaptive-difficulty tracker.
    Mirrors the DB-writing block inside chat_endpoint so both the
    synchronous and streaming endpoints behave identically once the
    reply text is known.
    """
    session_id = await _get_or_create_active_session(user_id, user_message)

    await execute(
        "INSERT INTO chat_messages (user_id, session_id, message_type, content, metadata) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, session_id, 'user', user_message,
         json.dumps({"page_url": page_url, "topic": topic_key}))
    )

    metadata = {"page_url": page_url, "topic": topic_key}
    if suggestions:
        metadata["suggestions"] = suggestions

    assistant_message_id = await execute(
        "INSERT INTO chat_messages (user_id, session_id, message_type, content, metadata) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, session_id, 'assistant', reply, json.dumps(metadata))
    )

    await execute(
        "UPDATE chat_sessions SET updated_at = strftime('%s','now') WHERE session_id = ?",
        (session_id,)
    )

    difficulty_level = "intermediate"
    try:
        updated_progress = await record_topic_message(user_id, topic_key)
        difficulty_level = updated_progress.get("difficulty_level", difficulty_level)
    except Exception as e:
        import logging
        logging.error(f"Failed to update topic progress: {str(e)}")

    return {
        "session_id": session_id,
        "message_id": assistant_message_id,
        "difficulty": difficulty_level,
    }


# ── Endpoint Handlers ─────────────────────────────────────────────────────────

async def create_session(request: Request):
    """POST /api/chat/sessions - Create a new chat session"""
    user_id = await get_user_id(request)
    if isinstance(user_id, JSONResponse):
        return user_id

    # FIX: always attempt to parse JSON, regardless of content-type header
    try:
        body = await request.json()
    except Exception:
        body = {}

    title = body.get('title', 'New Chat')

    session_id = str(uuid.uuid4())

    await execute(
        "INSERT INTO chat_sessions (user_id, session_id, title, updated_at) "
        "VALUES (?, ?, ?, strftime('%s','now'))",
        (user_id, session_id, title)
    )

    session = await fetchone(
        "SELECT id, user_id, session_id, title, is_active, created_at, updated_at "
        "FROM chat_sessions WHERE session_id = ?",
        (session_id,)
    )

    return json_response({"success": True, "data": session})


async def get_sessions(request: Request):
    """GET /api/chat/sessions - Get all chat sessions for the current user"""
    user_id = await get_user_id(request)
    if isinstance(user_id, JSONResponse):
        return user_id

    limit = int(request.query_params.get('limit', 20))
    limit = max(1, min(100, limit))

    sessions = await fetchall(
        """
        SELECT
            cs.id, cs.user_id, cs.session_id, cs.title, cs.is_active,
            cs.created_at, cs.updated_at,
            (SELECT COUNT(*) FROM chat_messages WHERE session_id = cs.session_id) as message_count,
            (SELECT MAX(created_at) FROM chat_messages WHERE session_id = cs.session_id) as last_message_at
        FROM chat_sessions cs
        WHERE cs.user_id = ? AND cs.is_active = 1
        ORDER BY cs.updated_at DESC
        LIMIT ?
        """,
        (user_id, limit)
    )

    return json_response({"success": True, "data": sessions})


async def get_conversation_history(request: Request):
    """GET /api/chat/history/{session_id} - Get conversation history for a session"""
    user_id = await get_user_id(request)
    if isinstance(user_id, JSONResponse):
        return user_id

    session_id = request.path_params.get('session_id')
    if not session_id:
        return json_response({"detail": "session_id required"}, 400)

    limit = int(request.query_params.get('limit', 50))
    limit = max(1, min(200, limit))
    offset = int(request.query_params.get('offset', 0))
    offset = max(0, offset)

    # Validate session
    session = await validate_session(user_id, session_id)
    if not session:
        return json_response({"detail": "Session not found"}, 404)

    # Get messages (ordered by created_at DESC for latest first)
    messages = await fetchall(
        """
        SELECT id, user_id, session_id, message_type, content, metadata, created_at
        FROM chat_messages
        WHERE user_id = ? AND session_id = ?
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """,
        (user_id, session_id, limit, offset)
    )

    # Get total count
    total = await scalar(
        "SELECT COUNT(*) FROM chat_messages WHERE user_id = ? AND session_id = ?",
        (user_id, session_id)
    )

    # Parse metadata JSON for each message
    for msg in messages:
        if msg.get('metadata'):
            try:
                msg['metadata'] = json.loads(msg['metadata'])
            except Exception:
                msg['metadata'] = {}

    return json_response({
        "success": True,
        "data": {
            "session": session,
            "messages": messages,
            "total_count": total or 0,
            "limit": limit,
            "offset": offset
        }
    })


async def save_message(request: Request):
    """POST /api/chat/messages - Save a chat message"""
    user_id = await get_user_id(request)
    if isinstance(user_id, JSONResponse):
        return user_id

    try:
        body = await request.json()
    except Exception:
        return json_response({"detail": "Invalid JSON body"}, 400)

    session_id   = body.get('session_id')
    message_type = body.get('message_type')
    content      = body.get('content')
    metadata     = body.get('metadata', {})

    # Validate required fields
    if not all([session_id, message_type, content]):
        return json_response(
            {"detail": "session_id, message_type, and content are required"},
            400
        )

    # Validate message_type
    if message_type not in ['user', 'assistant', 'system']:
        return json_response(
            {"detail": "message_type must be 'user', 'assistant', or 'system'"},
            400
        )

    # Validate session exists and belongs to user
    session = await validate_session(user_id, session_id)
    if not session:
        return json_response({"detail": "Session not found"}, 404)

    # Save message
    metadata_json = json.dumps(metadata or {})

    # FIX: use the returned rowid instead of last_insert_rowid() across connections
    message_id = await execute(
        "INSERT INTO chat_messages (user_id, session_id, message_type, content, metadata) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, session_id, message_type, content, metadata_json)
    )

    # Update session's updated_at timestamp
    await execute(
        "UPDATE chat_sessions SET updated_at = strftime('%s','now') WHERE session_id = ?",
        (session_id,)
    )

    # FIX: fetch by the actual rowid, not last_insert_rowid() on a new connection
    message = await fetchone(
        "SELECT id, user_id, session_id, message_type, content, metadata, created_at "
        "FROM chat_messages WHERE id = ?",
        (message_id,)
    )

    if message and message.get('metadata'):
        try:
            message['metadata'] = json.loads(message['metadata'])
        except Exception:
            message['metadata'] = {}

    return json_response({"success": True, "data": message})


async def update_session_title(request: Request):
    """PUT /api/chat/sessions/{session_id} - Update session title"""
    user_id = await get_user_id(request)
    if isinstance(user_id, JSONResponse):
        return user_id

    session_id = request.path_params.get('session_id')
    if not session_id:
        return json_response({"detail": "session_id required"}, 400)

    try:
        body = await request.json()
    except Exception:
        return json_response({"detail": "Invalid JSON body"}, 400)

    title = body.get('title')
    if not title:
        return json_response({"detail": "title is required"}, 400)

    # Validate session exists and belongs to user
    session = await validate_session(user_id, session_id)
    if not session:
        return json_response({"detail": "Session not found"}, 404)

    await execute(
        "UPDATE chat_sessions SET title = ?, updated_at = strftime('%s','now') "
        "WHERE user_id = ? AND session_id = ? AND is_active = 1",
        (title, user_id, session_id)
    )

    updated_session = await fetchone(
        "SELECT id, user_id, session_id, title, is_active, created_at, updated_at "
        "FROM chat_sessions WHERE user_id = ? AND session_id = ?",
        (user_id, session_id)
    )

    return json_response({"success": True, "data": updated_session})


async def delete_session(request: Request):
    """DELETE /api/chat/sessions/{session_id} - Delete a chat session (soft delete)"""
    user_id = await get_user_id(request)
    if isinstance(user_id, JSONResponse):
        return user_id

    session_id = request.path_params.get('session_id')
    if not session_id:
        return json_response({"detail": "session_id required"}, 400)

    # Validate session exists and belongs to user
    session = await validate_session(user_id, session_id)
    if not session:
        return json_response({"detail": "Session not found"}, 404)

    # Soft delete
    await execute(
        "UPDATE chat_sessions SET is_active = 0, updated_at = strftime('%s','now') "
        "WHERE user_id = ? AND session_id = ? AND is_active = 1",
        (user_id, session_id)
    )

    return json_response({"success": True, "message": "Session deleted successfully"})


async def get_session_messages(request: Request):
    """GET /api/chat/sessions/{session_id}/messages - Alias for history"""
    return await get_conversation_history(request)

#chat endpoint function
async def chat_endpoint(request: Request):
    """
    POST /api/chat - Main chat endpoint that combines LLM calls with DB storage

    Accepts: { messages, context, topic_key, page_url }
    Returns: { reply, suggestions, message_id, difficulty }

    If authenticated: saves user message and assistant reply to DB, and
    updates the CB-18 adaptive-difficulty tracker for the topic.
    """
    # CB-11/CB-14: Check rate limits before proceeding
    user_id = None
    try:
        user_id = require_user(request)
    except Exception:
        pass  # Guest user

    rate_limit_error = await _rate_limiter.check_limit(request, user_id)
    if rate_limit_error:
        return json_response(rate_limit_error, status_code=429)

    try:
        body = await request.json()
    except Exception:
        return json_response({"detail": "Invalid JSON body"}, 400)

    messages  = body.get('messages', [])
    context   = body.get('context', '')
    # CB-18: short, stable topic key for progress tracking (distinct from the
    # long descriptive `context` string that gets fed to the LLM as flavor text)
    topic_key = (body.get('topic_key') or context or 'general').strip().lower()
    page_url  = body.get('page_url', '/')

    if not messages:
        return json_response({"detail": "messages array is required"}, 400)

    # Extract the latest user message
    user_message = None
    if messages and isinstance(messages, list):
        for msg in reversed(messages):
            if msg.get('role') == 'user':
                user_message = msg.get('content', '')
                break

    if not user_message:
        return json_response({"detail": "No user message found"}, 400)

    # CB-18: look up the student's current difficulty level for this topic.
    # CB-13: also fetch the active session's summary if available.
    # Guests have no persisted history, so they always get the default.
    difficulty_level = "intermediate"
    session_summary = ""
    if user_id:
        try:
            progress = await get_topic_progress(user_id, topic_key)
            difficulty_level = progress.get("difficulty_level", "intermediate")
        except Exception as e:
            import logging
            logging.error(f"Failed to load topic progress: {str(e)}")

        try:
            # CB-13: fetch the active session's summary
            active_session = await fetchone(
                "SELECT summary FROM chat_sessions "
                "WHERE user_id = ? AND is_active = 1 "
                "ORDER BY updated_at DESC LIMIT 1",
                (user_id,)
            )
            if active_session and active_session.get("summary"):
                session_summary = active_session["summary"]
        except Exception as e:
            import logging
            logging.warning(f"Failed to load session summary: {str(e)}")

    # Call the aiService chatbot
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            ai_response = await client.post(
                f"{AI_SERVICE_URL}/chat",
                json={
                    "message": user_message,
                    "topic": context or "",
                    "difficulty": difficulty_level,  # CB-18
                    "history": messages[:-1] if len(messages) > 1 else [],
                    "summary": session_summary  # CB-13: pass session summary
                }
            )
            ai_response.raise_for_status()
            ai_data = ai_response.json()

            reply       = ai_data.get('answer', '')
            suggestions = ai_data.get('suggestions', [])
            assistant_message_id = None

            # If user is authenticated, save to database and handle summarization
            # (inside httpx context so we can call /summarize if needed)
            if user_id:
                try:
                    # Get or create active session
                    active_session = await fetchone(
                        "SELECT session_id FROM chat_sessions "
                        "WHERE user_id = ? AND is_active = 1 "
                        "ORDER BY updated_at DESC LIMIT 1",
                        (user_id,)
                    )

                    if not active_session:
                        # Create new session
                        session_id = str(uuid.uuid4())
                        title = user_message[:50] + ('...' if len(user_message) > 50 else '')
                        await execute(
                            "INSERT INTO chat_sessions (user_id, session_id, title, updated_at) "
                            "VALUES (?, ?, ?, strftime('%s','now'))",
                            (user_id, session_id, title)
                        )
                    else:
                        session_id = active_session['session_id']

                    # Save user message (CB-18: tag with topic_key for later linkage)
                    await execute(
                        "INSERT INTO chat_messages (user_id, session_id, message_type, content, metadata) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (user_id, session_id, 'user', user_message,
                         json.dumps({"page_url": page_url, "topic": topic_key}))
                    )

                    # Save assistant reply
                    # FIX: capture the rowid directly so we can return message_id to the frontend
                    metadata = {"page_url": page_url, "topic": topic_key}
                    if suggestions:
                        metadata["suggestions"] = suggestions

                    assistant_message_id = await execute(
                        "INSERT INTO chat_messages (user_id, session_id, message_type, content, metadata) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (user_id, session_id, 'assistant', reply, json.dumps(metadata))
                    )

                    # Update session timestamp
                    await execute(
                        "UPDATE chat_sessions SET updated_at = strftime('%s','now') WHERE session_id = ?",
                        (session_id,)
                    )

                    # CB-13: Session summarization — re-summarize every N messages
                    # (inside client context so we can call /summarize)
                    try:
                        count = await scalar("SELECT COUNT(*) FROM chat_messages WHERE session_id = ?", (session_id,))
                        session_row = await fetchone(
                            "SELECT summary, summary_through_count FROM chat_sessions WHERE session_id = ?",
                            (session_id,)
                        )
                        if session_row:
                            summary = session_row.get("summary", "")
                            summarized_through = session_row.get("summary_through_count", 0) or 0

                            N = 10  # re-summarize every 10 new messages
                            if count and (count - summarized_through) >= N:
                                older = await fetchall(
                                    "SELECT message_type as role, content FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC LIMIT ?",
                                    (session_id, count - 10)  # everything except the most recent 10 turns
                                )
                                if older:
                                    try:
                                        resp = await client.post(
                                            f"{AI_SERVICE_URL}/summarize",
                                            json={"messages": older, "previous_summary": summary}
                                        )
                                        resp.raise_for_status()
                                        new_summary = resp.json().get("summary", summary)
                                        await execute(
                                            "UPDATE chat_sessions SET summary = ?, summary_through_count = ? WHERE session_id = ?",
                                            (new_summary, count, session_id)
                                        )
                                    except Exception as e:
                                        import logging
                                        logging.warning(f"Failed to summarize session {session_id}: {str(e)}")
                    except Exception as e:
                        import logging
                        logging.warning(f"Failed to check summarization trigger: {str(e)}")

                    # CB-18: log this turn against the topic's adaptive-difficulty tracker
                    try:
                        updated_progress = await record_topic_message(user_id, topic_key)
                        difficulty_level = updated_progress.get("difficulty_level", difficulty_level)
                    except Exception as e:
                        import logging
                        logging.error(f"Failed to update topic progress: {str(e)}")
                except Exception as e:
                    # Log error but don't fail the request - user still gets their answer
                    import logging
                    logging.error(f"Failed to save chat to DB: {str(e)}")

    except httpx.TimeoutException:
        return json_response(
            {"detail": "AI service timeout - please try again"},
            504
        )
    except httpx.HTTPError as e:
        return json_response(
            {"detail": f"AI service error: {str(e)}"},
            502
        )
    except Exception as e:
        return json_response(
            {"detail": f"Failed to reach AI service: {str(e)}"},
            500
        )

    # FIX: include message_id and session_id in response so frontend can submit CB-12 feedback
    return json_response({
        "reply":       reply,
        "suggestions": suggestions,
        "message_id":  assistant_message_id,  # None for guests; frontend should handle both
        "session_id":  session_id if user_id and 'session_id' in locals() else None,  # For CB-19 export
        "difficulty":  difficulty_level        # CB-18
    })


# ── T5: SSE Streaming Endpoint ────────────────────────────────────────────────

async def chat_stream_endpoint(request: Request):
    """
    POST /api/chat/stream

    SSE version of chat_endpoint. Streams the assistant's reply as it's
    generated, coalescing tokens on a fixed FLUSH_INTERVAL cadence so the
    client sees smooth, evenly-paced chunks instead of one giant blob or
    a flood of single-token events.

    Requires aiService to expose a matching streaming endpoint at
    POST {AI_SERVICE_URL}/chat/stream that emits SSE frames shaped like:
        data: {"delta": "<token text>"}
    ending the stream when the generator completes (or emitting a final
    frame with a "done" key). If that endpoint doesn't exist yet, this
    will surface a clean SSE "error" event rather than crashing.

    Same request contract as /chat: { messages, context, topic_key, page_url }

    Emits SSE events:
        event: message  data: {"delta": "..."}          (repeated)
        event: done      data: {"message_id", "session_id", "difficulty", "suggestions"}
        event: error      data: {"error": "..."}          (on failure)
    """
    user_id = None
    try:
        user_id = require_user(request)
    except Exception:
        pass  # Guest user

    rate_limit_error = await _rate_limiter.check_limit(request, user_id)
    if rate_limit_error:
        return json_response(rate_limit_error, status_code=429)

    try:
        body = await request.json()
    except Exception:
        return json_response({"detail": "Invalid JSON body"}, 400)

    messages  = body.get('messages', [])
    context   = body.get('context', '')
    topic_key = (body.get('topic_key') or context or 'general').strip().lower()
    page_url  = body.get('page_url', '/')

    if not messages:
        return json_response({"detail": "messages array is required"}, 400)

    user_message = None
    for msg in reversed(messages):
        if msg.get('role') == 'user':
            user_message = msg.get('content', '')
            break
    if not user_message:
        return json_response({"detail": "No user message found"}, 400)

    difficulty_level = "intermediate"
    session_summary = ""
    if user_id:
        try:
            progress = await get_topic_progress(user_id, topic_key)
            difficulty_level = progress.get("difficulty_level", "intermediate")
        except Exception as e:
            import logging
            logging.error(f"Failed to load topic progress: {str(e)}")
        try:
            active_session = await fetchone(
                "SELECT summary FROM chat_sessions "
                "WHERE user_id = ? AND is_active = 1 "
                "ORDER BY updated_at DESC LIMIT 1",
                (user_id,)
            )
            if active_session and active_session.get("summary"):
                session_summary = active_session["summary"]
        except Exception as e:
            import logging
            logging.warning(f"Failed to load session summary: {str(e)}")

    async def event_generator() -> AsyncGenerator[str, None]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=STREAM_QUEUE_MAX)
        full_reply_parts: list = []
        suggestions: list = []
        upstream_error: Optional[str] = None

        async def producer():
            nonlocal upstream_error
            try:
                async with httpx.AsyncClient(timeout=None) as client:
                    async with client.stream(
                        "POST",
                        f"{AI_SERVICE_URL}/chat/stream",
                        json={
                            "message": user_message,
                            "topic": context or "",
                            "difficulty": difficulty_level,
                            "history": messages[:-1] if len(messages) > 1 else [],
                            "summary": session_summary,
                        },
                    ) as resp:
                        resp.raise_for_status()
                        async for line in resp.aiter_lines():
                            if not line or not line.startswith("data:"):
                                continue
                            raw = line[len("data:"):].strip()
                            if not raw:
                                continue
                            try:
                                data = json.loads(raw)
                            except Exception:
                                continue
                            # Tolerant of a few likely key names from aiService
                            token = (
                                data.get("delta")
                                or data.get("token")
                                or data.get("text")
                                or ""
                            )
                            if data.get("suggestions"):
                                suggestions.extend(data["suggestions"])
                            if token:
                                full_reply_parts.append(token)
                                await queue.put(token)
            except httpx.HTTPError as e:
                upstream_error = f"AI service error: {str(e)}"
            except Exception as e:
                upstream_error = f"Failed to reach AI service: {str(e)}"
            finally:
                await queue.put(None)

        producer_task = asyncio.create_task(producer())

        last_flush = time.monotonic()
        buffer: list = []
        done = False
        try:
            while not done:
                if await request.is_disconnected():
                    producer_task.cancel()
                    return

                timeout = max(0.0, FLUSH_INTERVAL - (time.monotonic() - last_flush))
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=timeout or FLUSH_INTERVAL)
                    if item is None:
                        done = True
                    else:
                        buffer.append(item)
                except asyncio.TimeoutError:
                    pass

                now = time.monotonic()
                if buffer and (now - last_flush >= FLUSH_INTERVAL or done):
                    chunk = "".join(buffer)
                    buffer.clear()
                    last_flush = now
                    yield sse_format(json.dumps({"delta": chunk}), event="message")
                elif not buffer and (now - last_flush) >= HEARTBEAT_INTERVAL:
                    last_flush = now
                    yield ": heartbeat\n\n"

            if upstream_error:
                yield sse_format(json.dumps({"error": upstream_error}), event="error")
                return

            reply = "".join(full_reply_parts)
            result = {"suggestions": suggestions, "difficulty": difficulty_level}

            if user_id and reply:
                try:
                    persisted = await _persist_turn(
                        user_id, user_message, reply, suggestions, topic_key, page_url
                    )
                    result.update(persisted)
                except Exception as e:
                    import logging
                    logging.error(f"Failed to save streamed chat to DB: {str(e)}")

            yield sse_format(json.dumps({"done": True, **result}), event="done")

        finally:
            if not producer_task.done():
                producer_task.cancel()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable Nginx buffering for this route
        },
    )


# ── CB-12: Feedback Endpoint ──────────────────────────────────────────────────

async def submit_feedback(request: Request):
    """
    POST /api/chat/feedback
    CB-12 — Persist thumbs-up / thumbs-down votes from authenticated users.
    Also feeds CB-18's adaptive-difficulty tracker: a like nudges the
    topic's level up, a dislike pulls it back down.

    Request body (JSON):
        {
            "message_id":  <int>,
            "session_id":  "<uuid>",
            "feedback":    "like" | "dislike"
        }

    Returns 200 on success, 400 on bad input, 401 if unauthenticated,
    404 if the message doesn't belong to the user's session.
    """
    # Auth guard
    user_id = require_user(request)
    if user_id is None:
        return json_response({"detail": "Not authenticated"}, 401)

    # Parse body
    try:
        body = await request.json()
    except Exception:
        return json_response({"detail": "Invalid JSON body"}, 400)

    message_id = body.get("message_id")
    session_id = body.get("session_id")
    feedback   = body.get("feedback")

    # Validate required fields
    if not all([message_id, session_id, feedback]):
        return json_response(
            {"detail": "message_id, session_id, and feedback are required"},
            400
        )

    if feedback not in ("like", "dislike"):
        return json_response(
            {"detail": "feedback must be 'like' or 'dislike'"},
            400
        )

    if not isinstance(message_id, int):
        return json_response(
            {"detail": "message_id must be an integer"},
            400
        )

    # Verify the message exists and belongs to this user's session
    message = await fetchone(
        """
        SELECT cm.id, cm.user_id, cm.session_id, cm.metadata
        FROM   chat_messages cm
        JOIN   chat_sessions  cs ON cs.session_id = cm.session_id
        WHERE  cm.id         = ?
          AND  cm.session_id = ?
          AND  cs.user_id    = ?
          AND  cs.is_active  = 1
        """,
        (message_id, session_id, user_id)
    )

    if not message:
        return json_response(
            {"detail": "Message not found or does not belong to your session"},
            404
        )

    # Upsert feedback
    await upsert_feedback(
        message_id=message_id,
        user_id=user_id,
        session_id=session_id,
        feedback=feedback
    )

    saved = await get_feedback_for_message(message_id, user_id)

    # CB-18: feed this rating into the topic's adaptive-difficulty tracker
    try:
        msg_topic = "general"
        if message.get("metadata"):
            msg_topic = json.loads(message["metadata"]).get("topic", "general")
        await record_topic_feedback(user_id, msg_topic, feedback)
    except Exception as e:
        import logging
        logging.error(f"Failed to update topic progress from feedback: {str(e)}")

    return json_response({
        "success": True,
        "data": {
            "message_id": message_id,
            "feedback":   saved["feedback"],
            "created_at": saved["created_at"]
        }
    })


# ── CB-18: Adaptive Difficulty Endpoints ──────────────────────────────────────

async def get_progress(request: Request):
    """GET /api/chat/progress - every topic's tracked difficulty level for this student"""
    user_id = await get_user_id(request)
    if isinstance(user_id, JSONResponse):
        return user_id

    progress = await get_all_topic_progress(user_id)
    return json_response({"success": True, "data": progress})


async def get_topic_progress_endpoint(request: Request):
    """GET /api/chat/progress/{topic} - difficulty level for a single topic"""
    user_id = await get_user_id(request)
    if isinstance(user_id, JSONResponse):
        return user_id

    topic = request.path_params.get('topic')
    if not topic:
        return json_response({"detail": "topic required"}, 400)

    progress = await get_topic_progress(user_id, topic)
    return json_response({"success": True, "data": progress})


# ── CB-19: Session Export & Study Sheet Generation ────────────────────────────

async def export_session(request: Request):
    """
    GET /api/chat/sessions/{session_id}/export
    Compiles the session's message history into a downloadable Markdown
    study sheet: a "key formulas" digest pulled from display-LaTeX blocks,
    followed by the full Q&A trail.
    """
    user_id = await get_user_id(request)
    if isinstance(user_id, JSONResponse):
        return user_id

    session_id = request.path_params.get('session_id')
    if not session_id:
        return json_response({"detail": "session_id required"}, 400)

    session = await validate_session(user_id, session_id)
    if not session:
        return json_response({"detail": "Session not found"}, 404)

    messages = await fetchall(
        "SELECT message_type, content, created_at FROM chat_messages "
        "WHERE user_id = ? AND session_id = ? ORDER BY created_at ASC",
        (user_id, session_id)
    )

    study_sheet = build_study_sheet(session, messages)
    safe_title = re.sub(
        r"[^a-zA-Z0-9\-_]+", "_", (session.get("title") or "study-sheet")
    ).strip("_") or "study-sheet"

    return Response(
        content=study_sheet,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{safe_title}.md"'}
    )


# ── Routes ────────────────────────────────────────────────────────────────────

routes = [
    Route("/",                           chat_endpoint,              methods=["POST"]),
    Route("/stream",                    chat_stream_endpoint,       methods=["POST"]),  # T5
    Route("/sessions",                       create_session,             methods=["POST"]),
    Route("/sessions",                       get_sessions,               methods=["GET"]),
    Route("/sessions/{session_id}",          update_session_title,       methods=["PUT"]),
    Route("/sessions/{session_id}",          delete_session,             methods=["DELETE"]),
    Route("/messages",                       save_message,               methods=["POST"]),
    Route("/history/{session_id}",           get_conversation_history,   methods=["GET"]),
    Route("/sessions/{session_id}/messages", get_session_messages,       methods=["GET"]),
    Route("/sessions/{session_id}/export",   export_session,             methods=["GET"]),  # CB-19
    Route("/feedback",                       submit_feedback,            methods=["POST"]),  # CB-12
    Route("/progress",                       get_progress,               methods=["GET"]),   # CB-18
    Route("/progress/{topic}",               get_topic_progress_endpoint, methods=["GET"]),  # CB-18
]
