import time

from onereside_chatbot.database.collections import idac
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


def save_user_message_only(phone_number: str, user_message: dict, whatsapp_username: str) -> None:
    """Append only the user's chat entry during human takeover (no bot response)."""
    try:
        content = format_user(user_message=user_message, phone_number=phone_number)
        idac.update_one(
            {"phone_number": phone_number},
            {
                "$push": {"chat_history": {"role": "user", "content": content}},
                "$set": {"updated_at": int(time.time()), "username": whatsapp_username},
            },
        )
        logger.info("User message saved (takeover mode)", extra={"phone_number": phone_number})
    except Exception as e:
        logger.exception("Failed to save user message", extra={"phone_number": phone_number, "exception": e})
        raise e


def save_agent_message(phone_number: str, agent_text: str) -> None:
    """Append a human agent's reply to chat_history."""
    try:
        idac.update_one(
            {"phone_number": phone_number},
            {
                "$push": {"chat_history": {"role": "assistant", "content": agent_text}},
                "$set": {"updated_at": int(time.time())},
            },
        )
        logger.info("Agent message saved", extra={"phone_number": phone_number})
    except Exception as e:
        logger.exception("Failed to save agent message", extra={"phone_number": phone_number, "exception": e})
        raise e
