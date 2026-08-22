ALLOWED_AI_ORIGINS = [
    "https://calculus.quantumlogicslimited.com",  # Production domain
    "https://www.calculus.quantumlogicslimited.com",  # WWW variant
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173"
]

# Add support for extra origins via env var (so we don't need a rebuild later)
import os
extra_origins = os.getenv("ALLOWED_AI_ORIGINS_EXTRA", "")
if extra_origins:
    for origin in extra_origins.split(","):
        origin = origin.strip()
        if origin and origin not in ALLOWED_AI_ORIGINS:
            ALLOWED_AI_ORIGINS.append(origin)
