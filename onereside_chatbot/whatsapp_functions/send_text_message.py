import json

import httpx

from onereside_chatbot.constants import GUPSHUP_SOURCE
from onereside_chatbot.utils.env_load import (
    gupshup_api_key,
    gupshup_app_name
)
from onereside_chatbot.utils.logger_config import logger


def send_text_message(phone_number: str, bot_response: str):
    """Sends a text message to a phone number."""
    logger.info(
        "Sending text message to phone number with message",
        extra={"phone_number": phone_number, "bot_response": bot_response},
    )
    
    source = GUPSHUP_SOURCE
    app_name = gupshup_app_name

    destination = f"{phone_number}"
    url = "https://api.gupshup.io/wa/api/v1/msg"

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "apikey": gupshup_api_key,
    }

    data = {
        "source": source,
        "destination": destination,
        "message": json.dumps(bot_response),
        "src.name": app_name,
    }

    try:
        response = httpx.post(url, headers=headers, data=data)
        logger.info(
            "Response",
            extra={
                "phone_number": phone_number,
                "response": response.json(),
            },
        )
        return response.json()
    except Exception as e:
        logger.error(
            "Error in sending text message",
            extra={"phone_number": phone_number, "error": e},
        )
        raise e
