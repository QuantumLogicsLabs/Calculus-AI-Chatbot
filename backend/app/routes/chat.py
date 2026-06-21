# routers/chat.py - Complete chat implementation for Starlette
import json
import uuid
import httpx
from typing import Optional, Dict, Any
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from auth_utils import require_user
from db import fetchone, fetchall, execute, scalar

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

# ── Endpoint Handlers ─────────────────────────────────────────────────────────

async def create_session(request: Request):
    """POST /api/chat/sessions - Create a new chat session"""
    user_id = await get_user_id(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    
    # Get title from body
    try:
        body = await request.json() if request.headers.get('content-type') == 'application/json' else {}
    except:
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
            except:
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
    except:
        return json_response({"detail": "Invalid JSON body"}, 400)
    
    session_id = body.get('session_id')
    message_type = body.get('message_type')
    content = body.get('content')
    metadata = body.get('metadata', {})
    
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
    
    await execute(
        "INSERT INTO chat_messages (user_id, session_id, message_type, content, metadata) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, session_id, message_type, content, metadata_json)
    )
    
    # Update session's updated_at timestamp
    await execute(
        "UPDATE chat_sessions SET updated_at = strftime('%s','now') WHERE session_id = ?",
        (session_id,)
    )
    
    # Get the saved message
    message = await fetchone(
        "SELECT id, user_id, session_id, message_type, content, metadata, created_at "
        "FROM chat_messages WHERE id = last_insert_rowid()"
    )
    
    if message and message.get('metadata'):
        try:
            message['metadata'] = json.loads(message['metadata'])
        except:
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
    except:
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
    
    Accepts: { messages, context, page_url }
    Returns: { reply, suggestions }
    
    If authenticated: saves user message and assistant reply to DB
    """
    try:
        body = await request.json()
    except:
        return json_response({"detail": "Invalid JSON body"}, 400)
    
    messages = body.get('messages', [])
    context = body.get('context', '')
    page_url = body.get('page_url', '/')
    
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
    except:
        pass  # Guest user
    
    # Call the aiService chatbot
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            ai_response = await client.post(
                f"{AI_SERVICE_URL}/chat",
                json={
                    "message": user_message,
                    "topic": context or "",
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
    
    reply = ai_data.get('answer', '')
    suggestions = ai_data.get('suggestions', [])
    
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
                # Generate title from first message (first 50 chars)
                title = user_message[:50] + ('...' if len(user_message) > 50 else '')
                await execute(
                    "INSERT INTO chat_sessions (user_id, session_id, title, updated_at) "
                    "VALUES (?, ?, ?, strftime('%s','now'))",
                    (user_id, session_id, title)
                )
            else:
                session_id = active_session['session_id']
            
            # Save user message
            await execute(
                "INSERT INTO chat_messages (user_id, session_id, message_type, content, metadata) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, session_id, 'user', user_message, json.dumps({"page_url": page_url}))
            )
            
            # Save assistant reply
            metadata = {"page_url": page_url}
            if suggestions:
                metadata["suggestions"] = suggestions
            
            await execute(
                "INSERT INTO chat_messages (user_id, session_id, message_type, content, metadata) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, session_id, 'assistant', reply, json.dumps(metadata))
            )
            
            # Update session timestamp
            await execute(
                "UPDATE chat_sessions SET updated_at = strftime('%s','now') WHERE session_id = ?",
                (session_id,)
            )
        except Exception as e:
            # Log error but don't fail the request - user still gets their answer
            import logging
            logging.error(f"Failed to save chat to DB: {str(e)}")
    
    return json_response({
        "reply": reply,
        "suggestions": suggestions
    })


# ── Routes ────────────────────────────────────────────────────────────────────

routes = [
    Route("/chat", chat_endpoint, methods=["POST"]),  # Main chat endpoint
    Route("/sessions", create_session, methods=["POST"]),
    Route("/sessions", get_sessions, methods=["GET"]),
    Route("/sessions/{session_id}", update_session_title, methods=["PUT"]),
    Route("/sessions/{session_id}", delete_session, methods=["DELETE"]),
    Route("/messages", save_message, methods=["POST"]),
    Route("/history/{session_id}", get_conversation_history, methods=["GET"]),
    Route("/sessions/{session_id}/messages", get_session_messages, methods=["GET"]),
]
