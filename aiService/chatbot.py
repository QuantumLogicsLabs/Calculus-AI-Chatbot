"""
aiService/chatbot.py - CalcVoyager AI Service
Starlette app exposing /chat, /chat/stream, /summarize.
"""
import json
import logging
import os
from typing import AsyncGenerator

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from aiService.services.llm_client import (
    ask_llm, ask_llm_stream, summarize_history, LLMUnavailable, response_metadata,
)

ALLOWED_AI_ORIGINS = [
    "https://calculus.quantumlogicslimited.com",
    "https://www.calculus.quantumlogicslimited.com",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
extra_origins = os.getenv("ALLOWED_AI_ORIGINS_EXTRA", "")
if extra_origins:
    for origin in extra_origins.split(","):
        origin = origin.strip()
        if origin and origin not in ALLOWED_AI_ORIGINS:
            ALLOWED_AI_ORIGINS.append(origin)


async def homepage(request: Request):
    return JSONResponse({"service": "CalcVoyager AI Service", "status": "running"})


async def health(request: Request):
    return JSONResponse({"status": "healthy", "mode": response_metadata()["mode"],
                         "provider_checked": False})


def _valid_chat_body(body):
    return (
        isinstance(body, dict) and isinstance(body.get("message"), str) and bool(body["message"].strip())
        and all(isinstance(body.get(key, ""), str) for key in ("topic", "summary", "difficulty"))
        and isinstance(body.get("history", []), list)
        and all(isinstance(item, dict) and item.get("role") in {"user", "assistant"}
                and isinstance(item.get("content"), str) for item in body.get("history", []))
    )


async def chat_endpoint(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"detail": "Invalid JSON body"}, status_code=400)

    if not _valid_chat_body(body):
        return JSONResponse({"detail": "A message and valid conversation history are required"}, status_code=400)
    message = body["message"]

    topic = body.get("topic", "")
    difficulty = body.get("difficulty", "intermediate")
    history = body.get("history", [])
    summary = body.get("summary", "")

    try:
        answer = await ask_llm(
            message=message, topic=topic, history=history,
            difficulty=difficulty, summary=summary,
        )
    except LLMUnavailable as exc:
        return JSONResponse({"detail": exc.public_message, "code": exc.code}, status_code=exc.status_code)
    except Exception as exc:
        logging.error("AI_CHAT_FAILED: type=%s", type(exc).__name__)
        return JSONResponse({"detail": "The tutor is temporarily unavailable. Please try again.",
                             "code": "ai_unavailable"}, status_code=503)

    return JSONResponse({"answer": answer, "suggestions": [], **response_metadata()})


async def chat_stream_endpoint(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"detail": "Invalid JSON body"}, status_code=400)

    if not _valid_chat_body(body):
        return JSONResponse({"detail": "A message and valid conversation history are required"}, status_code=400)
    message = body["message"]

    topic = body.get("topic", "")
    difficulty = body.get("difficulty", "intermediate")
    history = body.get("history", [])
    summary = body.get("summary", "")

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for token in ask_llm_stream(
                message=message, topic=topic, history=history,
                difficulty=difficulty, summary=summary,
            ):
                yield f"data: {json.dumps({'delta': token})}\n\n"
        except LLMUnavailable as exc:
            yield f"event: error\ndata: {json.dumps({'error': exc.public_message, 'code': exc.code})}\n\n"
            return
        except Exception as exc:
            logging.error("AI_STREAM_FAILED: type=%s", type(exc).__name__)
            yield f"event: error\ndata: {json.dumps({'error': 'The tutor is temporarily unavailable. Please try again.', 'code': 'ai_unavailable'})}\n\n"
            return
        yield f"data: {json.dumps({'done': True, **response_metadata()})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def summarize_endpoint(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"detail": "Invalid JSON body"}, status_code=400)

    if not isinstance(body, dict) or not isinstance(body.get("messages", []), list):
        return JSONResponse({"detail": "messages must be an array"}, status_code=400)
    messages = body.get("messages", [])
    previous_summary = body.get("previous_summary", "")

    try:
        summary = await summarize_history(messages, previous_summary)
    except LLMUnavailable as exc:
        return JSONResponse({"detail": exc.public_message, "code": exc.code}, status_code=exc.status_code)
    except Exception as exc:
        logging.error("AI_SUMMARY_FAILED: type=%s", type(exc).__name__)
        return JSONResponse({"detail": "Conversation summary is unavailable.", "code": "ai_unavailable"}, status_code=503)

    return JSONResponse({"summary": summary})


middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_AI_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
]

app = Starlette(
    debug=False,
    middleware=middleware,
    routes=[
        Route("/", homepage, methods=["GET"]),
        Route("/health", health, methods=["GET"]),
        Route("/chat", chat_endpoint, methods=["POST"]),
        Route("/chat/stream", chat_stream_endpoint, methods=["POST"]),
        Route("/summarize", summarize_endpoint, methods=["POST"]),
    ],
)
