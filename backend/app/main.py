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
# B-1 FIX: the placeholder "https://your-calculus-website.com" was never
# swapped for the real production domain, so the browser's CORS preflight
# (OPTIONS) never found a matching Origin and blocked every chat request
# before it reached the server (net::ERR_FAILED on /api/chat and
# /api/chat/stream, on every message).
ALLOWED_ORIGINS = [
    "https://calculus.quantumlogicslimited.com",  # Production domain (B-1 fix: was a placeholder)
    "http://localhost:3000",                      # Local React development mapping
    "http://127.0.0.1:3000",
    "http://localhost:5173",                      # Local Vite development mapping
    "http://127.0.0.1:5173"
]


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