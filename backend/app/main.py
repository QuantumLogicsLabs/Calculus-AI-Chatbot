"""
CalcVoyager Backend - Main Application
Starlette-based backend with chat integration
"""
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount, Route
from starlette.responses import JSONResponse

from backend.app.routes import chat

# ✅ SECURITY ARCHITECT UPDATE: Define allowed domains explicitly.
# TODO: replace with real production domain
ALLOWED_ORIGINS = [
    "https://calculus.quantumlogicslimited.com",  # Production domain
    "https://www.calculus.quantumlogicslimited.com",  # WWW variant
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173"
]

# Add support for extra origins via env var
import os
extra_origins = os.getenv("ALLOWED_ORIGINS_EXTRA", "")
if extra_origins:
    for origin in extra_origins.split(","):
        origin = origin.strip()
        if origin and origin not in ALLOWED_ORIGINS:
            ALLOWED_ORIGINS.append(origin)


async def homepage(request):
    """Health check endpoint"""
    return JSONResponse({
        "service": "CalcVoyager Backend",
        "status": "running",
        "endpoints": {
            "chat": "/api/chat",
            "chat_stream": "/api/chat/stream",
            "sessions": "/api/chat/sessions",
            "history": "/api/chat/history/{session_id}"
        }
    })


async def health(request):
    """Health check"""
    return JSONResponse({"status": "healthy"})


# CORS middleware configuration
middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,  # ✅ Restricting allow_origins to specified domains
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],  # ✅ Locked down from ["*"] to required API methods
        allow_headers=["Content-Type", "Authorization"],  # ✅ Explicitly defining safe headers
    )
]

# Application
app = Starlette(
    debug=False,  # ✅ SECURITY ARCHITECT UPDATE: Disabled debug mode to prevent data leaks in production
    middleware=middleware,
    routes=[
        Route("/", homepage, methods=["GET"]),
        Route("/health", health, methods=["GET"]),
        Mount("/api/chat", routes=chat.routes),
    ],
)
