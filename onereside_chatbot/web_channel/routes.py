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
from onereside_chatbot.database.message_utils import get_messages_page
from onereside_chatbot.orchestration.run_turn import run_turn
from onereside_chatbot.utils.pubsub import PubSubManager
from onereside_chatbot.web_channel.adapter import build_turn
from onereside_chatbot.web_channel.identity import resolve_user
from onereside_chatbot.web_channel.origin import extract_origin, validate_origin
from onereside_chatbot.web_channel.session import create_session, resolve_token

router = APIRouter(prefix="/web", tags=["web"])

_SSE_HEARTBEAT_INTERVAL = 25
_SESSION_RATE_LIMIT = 10
_SESSION_RATE_WINDOW = 60
_WEB_TURN_CAP = 50
_HISTORY_LIMIT = 50


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


def _history_item(doc: dict) -> dict | None:
    """Map a messages-collection doc to a widget-friendly bubble."""
    role = doc.get("role")
    msg_type = doc.get("type") or "text"
    content = doc.get("content") or ""
    raw = doc.get("raw") if isinstance(doc.get("raw"), dict) else {}
    ts = doc.get("timestamp")
    mid = doc.get("_id")

    if role == "user":
        text = content or (raw.get("text") or {}).get("body") or raw.get("text") or ""
        if isinstance(text, dict):
            text = text.get("body") or ""
        return {
            "id": mid,
            "role": "user",
            "type": "text",
            "text": text,
            "content": text,
            "timestamp": ts,
        }

    if role in ("assistant", "human_agent", "system"):
        # Prefer the stored bot_response part so ProductCard / quickreply hydrate.
        if role == "assistant" and raw and raw.get("type"):
            item = {"id": mid, "role": "bot", **raw, "timestamp": ts}
            if "text" not in item and content:
                item["text"] = content
                item["content"] = content
            return item
        text = content or raw.get("text") or ""
        return {
            "id": mid,
            "role": "bot" if role == "assistant" else "system",
            "type": msg_type if msg_type != "unknown" else "text",
            "text": text,
            "content": text,
            "timestamp": ts,
        }

    return None


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


@router.get("/history")
async def web_history(
    request: Request,
    authorization: str | None = Header(default=None),
    limit: int = 50,
):
    """Return recent conversation messages for the authenticated web session.

    Oldest-first for widget hydration after refresh / new tab.
    """
    user_ref = resolve_user(_bearer_user_ref(authorization, request))
    limit = max(1, min(int(limit or _HISTORY_LIMIT), _HISTORY_LIMIT))
    _total, docs = get_messages_page(user_ref, skip=0, limit=limit)
    # get_messages_page is newest-first; reverse for chronological UI.
    chronological = list(reversed(docs))
    items = []
    for doc in chronological:
        mapped = _history_item(doc)
        if mapped:
            items.append(mapped)

    profile = idac.find_one({"phone_number": user_ref}, {"identifiers": 1, "human_takeover": 1}) or {}
    identifiers = profile.get("identifiers") or {}
    return {
        "user_ref": user_ref,
        "identified": bool(identifiers.get("phone") or identifiers.get("email")),
        "is_taken_over": bool((profile.get("human_takeover") or {}).get("active")),
        "messages": items,
    }


@router.post("/message")
async def web_message(
    request: Request,
    body: MessageRequest,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
):
    if os.environ.get("WEB_KILL_SWITCH") == "1":
        raise HTTPException(status_code=503, detail="Web channel disabled")

    user_ref = resolve_user(_bearer_user_ref(authorization, request))
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
    user_ref = resolve_user(resolve_token(token, origin))
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
    user_ref = resolve_user(_bearer_user_ref(authorization, request))
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
