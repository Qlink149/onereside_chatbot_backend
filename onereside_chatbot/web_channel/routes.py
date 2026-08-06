"""HTTP routes for the web chat widget."""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections import defaultdict

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from onereside_chatbot.database.collections import idac, orders
from onereside_chatbot.orchestration.run_turn import run_turn
from onereside_chatbot.utils.pubsub import PubSubManager
from onereside_chatbot.web_channel.adapter import build_turn
from onereside_chatbot.web_channel.origin import extract_origin, validate_origin
from onereside_chatbot.web_channel.session import create_session, resolve_token

router = APIRouter(prefix="/web", tags=["web"])

_SSE_HEARTBEAT_INTERVAL = 25
_SESSION_RATE_LIMIT = 10
_SESSION_RATE_WINDOW = 60
_WEB_TURN_CAP = 50

# Simple in-memory IP rate limiter for POST /session (no slowapi).
_session_hits: dict[str, list[float]] = defaultdict(list)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_session_rate_limit(ip: str) -> None:
    now = time.time()
    window_start = now - _SESSION_RATE_WINDOW
    hits = [t for t in _session_hits[ip] if t >= window_start]
    if len(hits) >= _SESSION_RATE_LIMIT:
        _session_hits[ip] = hits
        raise HTTPException(status_code=429, detail="Too many sessions")
    hits.append(now)
    _session_hits[ip] = hits


def _bearer_user_ref(authorization: str | None, request: Request) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    origin = extract_origin(request)
    if origin:
        validate_origin(origin)
    return resolve_token(authorization.split(" ", 1)[1].strip(), origin)


class SessionRequest(BaseModel):
    brand_id: str | None = None


class MessageRequest(BaseModel):
    # Accept either free text or an action payload (adapter decides).
    text: str | None = None
    action: str | None = None
    product_id: str | None = None
    brand_id: str | None = None
    fields: dict | None = None


class IdentifyRequest(BaseModel):
    phone: str | None = None
    email: str | None = None
    intent: str = "enquiry"


@router.post("/session")
async def web_session(request: Request, body: SessionRequest | None = None):
    _check_session_rate_limit(_client_ip(request))
    brand_id = body.brand_id if body else None
    bound_origin = validate_origin(extract_origin(request))
    return create_session(brand_id=brand_id, bound_origin=bound_origin)


@router.post("/message")
async def web_message(
    request: Request,
    body: MessageRequest,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
):
    if os.environ.get("WEB_KILL_SWITCH") == "1":
        raise HTTPException(status_code=503, detail="Web channel disabled")

    user_ref = _bearer_user_ref(authorization, request)
    profile = idac.find_one({"phone_number": user_ref}) or {}
    turn_count = int(profile.get("web_turn_count") or 0)
    if turn_count >= _WEB_TURN_CAP:
        raise HTTPException(status_code=429, detail="Turn limit reached")

    payload = body.model_dump(exclude_none=True)
    if "text" not in payload and "action" not in payload:
        raise HTTPException(status_code=400, detail="text or action required")

    turn = build_turn(
        user_ref=user_ref,
        display_name=profile.get("username") or "Web User",
        payload=payload,
    )
    idac.update_one(
        {"phone_number": user_ref},
        {"$inc": {"web_turn_count": 1}},
        upsert=True,
    )
    background_tasks.add_task(run_turn, turn)
    return JSONResponse(content={"queued": True}, status_code=202)


@router.get("/stream")
async def web_stream(request: Request, token: str):
    """SSE stream keyed by web user_ref (no dashboard takeover auto-release)."""
    origin = extract_origin(request)
    if origin:
        validate_origin(origin)
    user_ref = resolve_token(token, origin)
    pubsub = PubSubManager()
    queue = pubsub.subscribe(user_ref)

    async def event_generator():
        try:
            yield f"data: {json.dumps({'type': 'connected', 'user_ref': user_ref})}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_SSE_HEARTBEAT_INTERVAL)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        except (asyncio.CancelledError, GeneratorExit):
            pass
        finally:
            pubsub.unsubscribe(user_ref, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/identify")
async def web_identify(
    request: Request,
    body: IdentifyRequest,
    authorization: str | None = Header(default=None),
):
    from onereside_chatbot.web_channel.identity import identify as identify_user

    origin = extract_origin(request)
    if origin:
        validate_origin(origin)
    user_ref = _bearer_user_ref(authorization, request)
    return identify_user(
        user_ref=user_ref,
        phone=body.phone,
        email=body.email,
        intent=body.intent or "enquiry",
        bound_origin=origin,
    )


@router.get("/order/{order_id}")
async def web_order(
    request: Request,
    order_id: str,
    authorization: str | None = Header(default=None),
):
    user_ref = _bearer_user_ref(authorization, request)
    doc = orders.find_one({"order_id": order_id, "phone_number": user_ref})
    if not doc:
        raise HTTPException(status_code=404, detail="Order not found")
    return {
        "order_id": doc.get("order_id"),
        "payment_status": doc.get("payment_status"),
        "amount_inr": doc.get("amount_inr"),
        "product": {
            "name": (doc.get("product") or {}).get("name"),
            "product_id": (doc.get("product") or {}).get("product_id"),
        },
        "created_at": doc.get("created_at"),
    }
