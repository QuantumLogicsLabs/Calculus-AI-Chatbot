"""
CalcVoyager Backend - Main Application
Starlette-based backend with chat integration
"""
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount
from starlette.responses import JSONResponse

from backend.app.routes import chat

# CORS middleware configuration
middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
]

# Application
app = Starlette(
    debug=True,
    middleware=middleware,
    routes=[
        Mount("/api/chat", routes=chat.routes),
    ]
)

@app.route("/")
async def homepage(request):
    """Health check endpoint"""
    return JSONResponse({
        "service": "CalcVoyager Backend",
        "status": "running",
        "endpoints": {
            "chat": "/api/chat",
            "sessions": "/api/chat/sessions",
            "history": "/api/chat/history/{session_id}"
        }
    })

@app.route("/health")
async def health(request):
    """Health check"""
    return JSONResponse({"status": "healthy"})
