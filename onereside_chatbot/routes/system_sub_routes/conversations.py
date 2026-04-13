import asyncio
import json
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from onereside_chatbot.database.conversation_utils import save_agent_message, set_takeover
from onereside_chatbot.database.user_utils import get_user_profile, update_agent_request_flag
from onereside_chatbot.routes.dependencies import verify_api_key
from onereside_chatbot.utils.logger_config import logger
from onereside_chatbot.utils.pubsub import PubSubManager
from onereside_chatbot.whatsapp_functions.send_text_message import send_text_message

router = APIRouter(prefix="/conversations", tags=["conversations"])

_SSE_HEARTBEAT_INTERVAL = 25  # seconds — keep-alive ping, below nginx's default 60s idle timeout


class SendMessageRequest(BaseModel):
    message: str


class TakeoverRequest(BaseModel):
    taken_by: str = "agent"


@router.get("/{phone_number}/stream")
async def stream_conversation(phone_number: str, _=Depends(verify_api_key)):
    """SSE stream — push new messages to dashboard in real time."""
    pubsub = PubSubManager()
    queue = pubsub.subscribe(phone_number)

    async def event_generator():
        try:
            # Initial connected event so the dashboard knows the stream is live
            yield f"data: {json.dumps({'type': 'connected', 'phone_number': phone_number})}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_SSE_HEARTBEAT_INTERVAL)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # SSE comment line — keeps the connection alive through proxies
                    yield ": ping\n\n"
        except (asyncio.CancelledError, GeneratorExit):
            pass
        finally:
            pubsub.unsubscribe(phone_number, queue)
            # Auto-release back to bot when agent disconnects (tab close, navigate away)
            try:
                profile = get_user_profile(phone_number)
                if profile and profile.get("human_takeover", {}).get("active"):
                    set_takeover(phone_number=phone_number, active=False, taken_by=None)
                    await pubsub.publish(
                        phone_number,
                        {
                            "type": "release",
                            "phone_number": phone_number,
                            "timestamp": int(time.time()),
                            "reason": "agent_disconnected",
                        },
                    )
                    logger.info("Auto-released to bot on agent disconnect", extra={"phone_number": phone_number})
            except Exception as e:
                logger.exception("Failed to auto-release on disconnect", extra={"phone_number": phone_number, "exception": e})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # tells nginx not to buffer this response
            "Connection": "keep-alive",
        },
    )


@router.get("/{phone_number}/history")
def get_conversation_history(phone_number: str, _=Depends(verify_api_key)):
    """Return full chat history for a user — used by dashboard on reconnect."""
    user = get_user_profile(phone_number)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "phone_number": phone_number,
        "username": user.get("username", ""),
        "chat_history": user.get("chat_history", []),
        "human_takeover": user.get("human_takeover", {"active": False}),
    }


AGENT_JOINED_MESSAGE = "You are now connected to a live support agent. How can we help you?"
AGENT_LEFT_MESSAGE = "You're back with the One Reside AI concierge — let me know if there's anything else I can help you with!"


@router.post("/{phone_number}/takeover")
async def takeover_conversation(
    phone_number: str,
    body: TakeoverRequest,
    _=Depends(verify_api_key),
):
    """Human agent takes over a conversation — bot goes silent."""
    user = get_user_profile(phone_number)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    set_takeover(phone_number=phone_number, active=True, taken_by=body.taken_by)

    # Send "agent joined" message to the user via WhatsApp
    send_text_message(
        phone_number=phone_number,
        bot_response={"type": "text", "text": AGENT_JOINED_MESSAGE},
    )
    save_agent_message(phone_number=phone_number, agent_text=AGENT_JOINED_MESSAGE)

    pubsub = PubSubManager()
    now = int(time.time())
    await pubsub.publish(
        phone_number,
        {"type": "takeover", "phone_number": phone_number, "taken_by": body.taken_by, "timestamp": now},
    )
    # Also surface the auto-message on the SSE stream
    await pubsub.publish(
        phone_number,
        {"type": "agent_message", "phone_number": phone_number, "content": AGENT_JOINED_MESSAGE, "timestamp": now},
    )
    logger.info("Conversation taken over", extra={"phone_number": phone_number, "taken_by": body.taken_by})
    return {"status": "ok", "message": f"Conversation taken over by {body.taken_by}"}


@router.post("/{phone_number}/release")
async def release_conversation(phone_number: str, _=Depends(verify_api_key)):
    """Release the conversation back to the bot."""
    user = get_user_profile(phone_number)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    set_takeover(phone_number=phone_number, active=False, taken_by=None)

    send_text_message(
        phone_number=phone_number,
        bot_response={"type": "text", "text": AGENT_LEFT_MESSAGE},
    )
    save_agent_message(phone_number=phone_number, agent_text=AGENT_LEFT_MESSAGE)

    pubsub = PubSubManager()
    now = int(time.time())
    await pubsub.publish(
        phone_number,
        {
            "type": "release",
            "phone_number": phone_number,
            "timestamp": now,
        },
    )
    await pubsub.publish(
        phone_number,
        {"type": "agent_message", "phone_number": phone_number, "content": AGENT_LEFT_MESSAGE, "timestamp": now},
    )
    logger.info("Conversation released to bot", extra={"phone_number": phone_number})
    return {"status": "ok", "message": "Conversation released back to bot"}


@router.post("/{phone_number}/send")
async def send_agent_message(
    phone_number: str,
    body: SendMessageRequest,
    _=Depends(verify_api_key),
):
    """Human agent sends a message to the user via WhatsApp."""
    user = get_user_profile(phone_number)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Enforce WhatsApp 24-hour conversation window
    last_activity = user.get("updated_at", 0)
    if time.time() - last_activity > 24 * 3600:
        raise HTTPException(
            status_code=400,
            detail="Cannot send message: WhatsApp 24-hour conversation window has expired. The user must message first.",
        )

    # Send via WhatsApp
    result = send_text_message(
        phone_number=phone_number,
        bot_response={"type": "text", "text": body.message},
    )
    if result.get("status") != "submitted":
        logger.warning("Agent message may not have been delivered", extra={"phone_number": phone_number, "result": result})

    # Persist to chat history
    save_agent_message(phone_number=phone_number, agent_text=body.message)

    # Publish to SSE so dashboard reflects the sent message
    pubsub = PubSubManager()
    await pubsub.publish(
        phone_number,
        {
            "type": "agent_message",
            "phone_number": phone_number,
            "content": body.message,
            "timestamp": int(time.time()),
        },
    )

    return {"status": "ok", "whatsapp_status": result.get("status")}


@router.post("/{phone_number}/resolve-agent-request")
def resolve_agent_request(phone_number: str, _=Depends(verify_api_key)):
    """Mark agent_request as resolved (False) once the team has connected with the user."""
    user = get_user_profile(phone_number)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    updated = update_agent_request_flag(user["_id"])
    if not updated:
        raise HTTPException(status_code=400, detail="Failed to resolve agent request")

    logger.info("Agent request resolved", extra={"phone_number": phone_number})
    return {"status": "ok", "message": "Agent request resolved"}