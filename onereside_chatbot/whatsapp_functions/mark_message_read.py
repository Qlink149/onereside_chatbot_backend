import httpx

from onereside_chatbot.utils.env_load import (
    gupshup_app_id,
    gupshup_token,
)
from onereside_chatbot.utils.logger_config import logger


def mark_message_read(message_id: str):
    """Marks an incoming WhatsApp message as read and shows the typing indicator."""
    url = f"https://partner.gupshup.io/partner/app/{gupshup_app_id}/v1/event"
    headers = {
        "Authorization": f"{gupshup_token}",
        "Content-Type": "application/json",
    }
    data = {
        "type": "message-event",
        "message": {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
            "typing_indicator": {"type": "text"},
        },
    }

    try:
        response = httpx.post(url, headers=headers, json=data)
        logger.info(
            "Marked message as read",
            extra={"message_id": message_id, "response": response.json()},
        )
        return response.json()
    except Exception as e:
        # Non-critical UX side effect — swallow errors so it never breaks the main pipeline.
        logger.error(
            "Error marking message as read",
            extra={"message_id": message_id, "error": e},
        )
