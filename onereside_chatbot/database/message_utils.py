"""Per-message store — one doc per sent/received WhatsApp message.

Unlike the embedded ``chat_history`` array on the user doc (kept as a small
rolling window for LLM context), this collection is append-only, paginated,
and carries the full debug ``context`` (classifier decision, agent, tool
calls) for the admin dashboard.
"""

import time
import uuid

from pymongo import DESCENDING

from onereside_chatbot.database.collections import messages
from onereside_chatbot.utils.format_chathistory import format_assistant, format_user
from onereside_chatbot.utils.logger_config import logger


def save_turn_messages(data: dict) -> None:
    """Persist the incoming user message and each bot response part as message docs.

    Never raises — a message-store failure must not break the reply flow.
    """
    phone_number = data.get("phone_number")
    try:
        now = int(time.time())
        turn_id = uuid.uuid4().hex
        trace = data.get("trace")
        docs = []

        user_message = data.get("messages")
        if user_message:
            try:
                content = format_user(user_message=user_message, phone_number=phone_number)
            except Exception:
                content = ""
            docs.append(
                {
                    "phone_number": phone_number,
                    "turn_id": turn_id,
                    "role": "user",
                    "type": user_message.get("type", "unknown"),
                    "content": content,
                    "raw": user_message,
                    "context": None,
                    "timestamp": data.get("received_at") or now,
                }
            )

        for part in data.get("bot_response", []):
            if part.get("type") == "skip":
                continue
            try:
                content = format_assistant(assistant_message=[part], phone_number=phone_number)
            except Exception:
                content = ""
            docs.append(
                {
                    "phone_number": phone_number,
                    "turn_id": turn_id,
                    "role": "assistant",
                    "type": part.get("type", "unknown"),
                    "content": content,
                    "raw": part,
                    "context": trace,
                    "timestamp": now,
                }
            )

        if docs:
            messages.insert_many(docs)
            logger.info(
                "Turn messages saved",
                extra={"phone_number": phone_number, "turn_id": turn_id, "count": len(docs)},
            )
    except Exception as e:
        logger.exception(
            "Failed to save turn messages",
            extra={"phone_number": phone_number, "exception": e},
        )


def save_single_message(
    phone_number: str,
    role: str,
    content: str,
    msg_type: str = "text",
    raw: dict | None = None,
    context: dict | None = None,
    timestamp: int | None = None,
) -> None:
    """Persist one message doc (human-takeover sends, agent joins, etc). Never raises."""
    try:
        messages.insert_one(
            {
                "phone_number": phone_number,
                "turn_id": None,
                "role": role,
                "type": msg_type,
                "content": content,
                "raw": raw,
                "context": context,
                "timestamp": timestamp or int(time.time()),
            }
        )
    except Exception as e:
        logger.exception(
            "Failed to save message",
            extra={"phone_number": phone_number, "role": role, "exception": e},
        )


def get_messages_page(phone_number: str, skip: int = 0, limit: int = 50) -> tuple[int, list]:
    """Paginated message docs for a user, newest first. Returns (total, docs)."""
    try:
        query = {"phone_number": phone_number}
        total = messages.count_documents(query)
        docs = list(
            messages.find(query)
            .sort([("timestamp", DESCENDING), ("_id", DESCENDING)])
            .skip(skip)
            .limit(limit)
        )
        for doc in docs:
            doc["_id"] = str(doc["_id"])
        return total, docs
    except Exception as e:
        logger.exception(
            "Failed to fetch messages page",
            extra={"phone_number": phone_number, "exception": e},
        )
        raise e
