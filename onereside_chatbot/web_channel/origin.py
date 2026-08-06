"""Web widget Origin / Referer validation (must match WEB_ALLOWED_ORIGINS)."""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import HTTPException, Request

from onereside_chatbot.utils.env_load import web_allowed_origins


def extract_origin(request: Request) -> str | None:
    origin = request.headers.get("origin")
    if origin:
        return origin.rstrip("/")
    referer = request.headers.get("referer")
    if referer:
        parsed = urlparse(referer)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    return None


def validate_origin(origin: str | None) -> str:
    if not origin:
        raise HTTPException(status_code=403, detail="Origin required")
    normalized = origin.rstrip("/")
    if normalized not in web_allowed_origins:
        raise HTTPException(status_code=403, detail="Origin not allowed")
    return normalized
