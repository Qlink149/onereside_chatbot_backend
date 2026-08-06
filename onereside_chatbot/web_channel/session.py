"""Web channel session create / resolve."""

from __future__ import annotations

from fastapi import HTTPException
from jose import JWTError, jwt

from onereside_chatbot.routes.system_sub_routes.auth import ALGORITHM
from onereside_chatbot.utils.env_load import jwt_secret, web_allowed_origins
from onereside_chatbot.web_channel.identity import create_anonymous


def create_session(brand_id: str | None = None, bound_origin: str | None = None) -> dict:
    """Create a web user doc, mint JWT, return {session_id, token}."""
    return create_anonymous(brand_id=brand_id, bound_origin=bound_origin)


def resolve_token(token: str, request_origin: str | None = None) -> str:
    """Decode and verify a web JWT; return user_ref (sub). Raises 401 on failure."""
    try:
        payload = jwt.decode(token, jwt_secret, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    if payload.get("channel") != "web":
        raise HTTPException(status_code=401, detail="Invalid token")
    user_ref = payload.get("sub")
    if not user_ref or not isinstance(user_ref, str):
        raise HTTPException(status_code=401, detail="Invalid token")

    bound = payload.get("origin")
    if bound:
        if not request_origin:
            raise HTTPException(status_code=401, detail="Origin required")
        if bound.rstrip("/") != request_origin.rstrip("/"):
            raise HTTPException(status_code=401, detail="Origin mismatch")
    if request_origin and request_origin.rstrip("/") not in web_allowed_origins:
        raise HTTPException(status_code=403, detail="Origin not allowed")

    return user_ref
