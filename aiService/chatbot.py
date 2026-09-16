"""
aiService/chatbot.py - CalcVoyager AI Service
Starlette app exposing /chat, /chat/stream, /summarize.
"""
import json
import os
from typing import AsyncGenerator

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from aiService.services.llm_client import ask_llm, ask_llm_stream, summarize_history

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
    return JSONResponse({"status": "healthy"})


async def chat_endpoint(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"detail": "Invalid JSON body"}, status_code=400)

    message = body.get("message", "")
    if not message:
        return JSONResponse({"detail": "message is required"}, status_code=400)

    topic = body.get("topic", "")
    difficulty = body.get("difficulty", "intermediate")
    history = body.get("history", [])
    summary = body.get("summary", "")

    try:
        answer = await ask_llm(
            message=message, topic=topic, history=history,
            difficulty=difficulty, summary=summary,
        )
    except Exception as e:
        return JSONResponse({"detail": f"LLM error: {str(e)}"}, status_code=502)

    return JSONResponse({"answer": answer, "suggestions": []})


async def chat_stream_endpoint(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"detail": "Invalid JSON body"}, status_code=400)

    message = body.get("message", "")
    if not message:
        return JSONResponse({"detail": "message is required"}, status_code=400)

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
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return
        yield "data: [DONE]\n\n"

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

    messages = body.get("messages", [])
    previous_summary = body.get("previous_summary", "")

    try:
        summary = await summarize_history(messages, previous_summary)
    except Exception as e:
        return JSONResponse({"detail": f"Summarize error: {str(e)}"}, status_code=502)

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
