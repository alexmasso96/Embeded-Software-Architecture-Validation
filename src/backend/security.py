"""
Per-session bearer-token auth (plan §3.3).

The worker binds 127.0.0.1 only, but other local users on a shared machine
could still reach the port. Every request must carry the session token the
parent process handed to the frontend at startup. The token lives in app.state
so tests can read it from the TestClient app.
"""
from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, Request, status


def generate_token() -> str:
    return secrets.token_urlsafe(32)


async def require_token(request: Request, authorization: str = Header(default="")) -> None:
    """FastAPI dependency: reject requests without the session bearer token.

    Accepts ``Authorization: Bearer <token>`` (the normal path) or, as a
    convenience for the SSE EventSource which can't set headers, a
    ``?token=<token>`` query param.
    """
    expected = request.app.state.token
    presented = ""
    if authorization.startswith("Bearer "):
        presented = authorization[len("Bearer "):]
    elif "token" in request.query_params:
        presented = request.query_params["token"]

    if not expected or not secrets.compare_digest(presented, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid session token.",
        )
