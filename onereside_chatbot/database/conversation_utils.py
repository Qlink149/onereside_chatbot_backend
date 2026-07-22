import time

from onereside_chatbot.constants import CHAT_HISTORY_MAX
from onereside_chatbot.database.collections import idac
from onereside_chatbot.database.message_utils import save_single_message
from onereside_chatbot.utils.format_chathistory import format_user
from onereside_chatbot.utils.logger_config import logger


def set_takeover(phone_number: str, active: bool, taken_by: str | None = None) -> None:
    """Set or clear the human takeover flag on a user document."""
    try:
        takeover_data = {
            "human_takeover.active": active,
            "human_takeover.taken_by": taken_by,
            "human_takeover.taken_at": int(time.time()) if active else None,
        }
        idac.update_one(
            {"phone_number": phone_number},
            {"$set": takeover_data},
        )
        logger.info(
            "Human takeover updated",
            extra={"phone_number": phone_number, "active": active, "taken_by": taken_by},
        )
    except Exception as e:
        logger.exception("Failed to set takeover", extra={"phone_number": phone_number, "exception": e})
        raise e


def save_user_message_only(phone_number: str, user_message: dict, whatsapp_username: str, received_at: int = None) -> None:
    """Append only the user's chat entry during human takeover (no bot response)."""
    try:
        content = format_user(user_message=user_message, phone_number=phone_number)
        now = int(time.time())
        idac.update_one(
            {"phone_number": phone_number},
            {
                "$push": {
                    "chat_history": {
                        "$each": [{"role": "user", "content": content, "timestamp": received_at or now}],
                        "$slice": -CHAT_HISTORY_MAX,
                    }
                },
                "$set": {"updated_at": now, "username": whatsapp_username},
            },
        )
        save_single_message(
            phone_number=phone_number,
            role="user",
            content=content,
            msg_type=user_message.get("type", "text"),
            raw=user_message,
            context={"source": "human_takeover"},
            timestamp=received_at or now,
        )
        logger.info("User message saved (takeover mode)", extra={"phone_number": phone_number})
    except Exception as e:
        logger.exception("Failed to save user message", extra={"phone_number": phone_number, "exception": e})
        raise e


def save_agent_message(phone_number: str, agent_text: str) -> None:
    """Append a human agent's reply to chat_history."""
    try:
        now = int(time.time())
        idac.update_one(
            {"phone_number": phone_number},
            {
                "$push": {
                    "chat_history": {
                        "$each": [{"role": "assistant", "content": agent_text, "timestamp": now}],
                        "$slice": -CHAT_HISTORY_MAX,
                    }
                },
                "$set": {"updated_at": now},
            },
        )
        save_single_message(
            phone_number=phone_number,
            role="human_agent",
            content=agent_text,
            msg_type="text",
            context={"source": "human_takeover"},
            timestamp=now,
        )
        logger.info("Agent message saved", extra={"phone_number": phone_number})
    except Exception as e:
        logger.exception("Failed to save agent message", extra={"phone_number": phone_number, "exception": e})
        raise e
