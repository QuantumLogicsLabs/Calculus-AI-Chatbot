# routers/chat.py - Complete chat implementation for Starlette
import json
import re
import uuid
import httpx
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
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


async def chat_endpoint(request: Request):
    """
    POST /api/chat - Main chat endpoint that combines LLM calls with DB storage

    Accepts: { messages, context, topic_key, page_url }
    Returns: { reply, suggestions, message_id, difficulty }

    If authenticated: saves user message and assistant reply to DB, and
    updates the CB-18 adaptive-difficulty tracker for the topic.
    """
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

    # Get user_id if authenticated (optional - guests can chat too)
    user_id = None
    try:
        user_id = require_user(request)
    except Exception:
        pass  # Guest user

    # CB-18: look up the student's current difficulty level for this topic.
    # Guests have no persisted history, so they always get the default.
    difficulty_level = "intermediate"
    if user_id:
        try:
            progress = await get_topic_progress(user_id, topic_key)
            difficulty_level = progress.get("difficulty_level", "intermediate")
        except Exception as e:
            import logging
            logging.error(f"Failed to load topic progress: {str(e)}")

    # Call the aiService chatbot
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            ai_response = await client.post(
                f"{AI_SERVICE_URL}/chat",
                json={
                    "message": user_message,
                    "topic": context or "",
                    "difficulty": difficulty_level,  # CB-18
                    "history": messages[:-1] if len(messages) > 1 else []
                }
            )
            ai_response.raise_for_status()
            ai_data = ai_response.json()
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

    reply       = ai_data.get('answer', '')
    suggestions = ai_data.get('suggestions', [])
    # FIX: track the assistant message_id so CB-12 feedback can reference it
    assistant_message_id = None

    # If user is authenticated, save to database
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

    # FIX: include message_id in response so frontend can submit CB-12 feedback
    return json_response({
        "reply":       reply,
        "suggestions": suggestions,
        "message_id":  assistant_message_id,  # None for guests; frontend should handle both
        "difficulty":  difficulty_level        # CB-18
    })


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
    Route("/chat",                           chat_endpoint,              methods=["POST"]),
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