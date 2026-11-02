"""
Request authentication for the chatbot routes.

The chatbot does not issue its own logins. It accepts the access token that
the main CalcVoyager backend (CalculusRuntime-Backend) gives a user at login
and reads the user id from it, so chat history belongs to the same account
the student uses on the website.

For this to work the chatbot must run with the SAME ``SECRET_KEY`` as the main
backend. When the chatbot is mounted inside the main backend that happens
automatically (same process, same environment). When it runs as its own
service, set ``SECRET_KEY`` to the main backend's value.

A missing, expired or invalid token means "guest": the user can still chat,
but nothing is saved to history.
"""
import logging
import os
from typing import Optional

import jwt
from starlette.requests import Request

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
_DEFAULT_SECRET = "change-me-in-production-use-a-long-random-string"


def _secret_key() -> str:
    # Read on each call so tests and the host app can set it after import.
    return os.getenv("SECRET_KEY", _DEFAULT_SECRET)


def _preview_mode() -> bool:
    return os.getenv("CALCVOYAGER_PREVIEW", "").lower() == "true"


def decode_token(token: str) -> Optional[int]:
    """Return the user id inside a main-backend access token, or None."""
    try:
        payload = jwt.decode(token, _secret_key(), algorithms=[ALGORITHM])
        return int(payload["sub"])
    except jwt.ExpiredSignatureError:
        logger.info("Chat auth: token expired; treating request as guest")
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        logger.info("Chat auth: invalid token; treating request as guest")
    return None


def require_user(request: Request) -> Optional[int]:
    """
    Return the logged-in user's id, or None for a guest.

    Guests can chat but have no saved sessions, history or feedback.
    Preview deployments (CALCVOYAGER_PREVIEW=true) always run as guest.
    """
    if _preview_mode():
        return None

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:].strip()
    if not token:
        return None
    return decode_token(token)
