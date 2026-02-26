import json

import httpx

from onereside_chatbot.constants import GUPSHUP_SOURCE
from onereside_chatbot.models.enums import ListIds
from onereside_chatbot.utils.env_load import (
    gupshup_api_key,
    gupshup_app_name,
)
from onereside_chatbot.utils.logger_config import logger


def send_service_list(phone_number):
    """Send a list message to a phone number."""
    url = "https://api.gupshup.io/wa/api/v1/msg"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "apikey": gupshup_api_key,
    }

    messages = (
        "Hello 😊\n\n"
        "I’m *Neha*, here to help you with details about PIMS City Hospital and to assist you in booking an appointment.\n\n"
        "To continue, please select one of the following options:\n"
    )

    message_json = json.dumps(
        {
            "type": "list",
            "title": "",
            "body": messages,
            "footer": "Managed by PIMS City Hospital.",
            "msgid": f"{ListIds.SERVICE_LIST_ID.value}",
            "globalButtons": [{"type": "text", "title": "Options"}],
            "items": [
                {
                    "title": "Options",
                    "subtitle": "option Subtitle",
                    "options": [
                        {
                            "type": "text",
                            "title": "Find a Doctor",
                            "description": "",
                            "postbackText": "register postback payload",
                        },
                        {
                            "type": "text",
                            "title": "Direction",
                            "description": "",
                            "postbackText": "register postback payload",
                        },
                        {
                            "type": "text",
                            "title": "Contact Us",
                            "description": "",
                            "postbackText": "register postback payload",
                        },
                        {
                            "type": "text",
                            "title": "Book an Appointment",
                            "description": "",
                            "postbackText": "register postback payload",
                        },
                        {
                            "type": "text",
                            "title": "Other",
                            "description": "",
                            "postbackText": "other postback payload",
                        },
                    ],
                }
            ],
        }
    )

    data = {
        "source": GUPSHUP_SOURCE,
        "destination": f"{phone_number}",
        "src.name": gupshup_app_name,
        "message": message_json,
    }

    try:
        response = httpx.post(url, headers=headers, data=data)
        logger.info(
            "Response from Gupshup API for sending service list",
            extra={"response": response.json()},
        )
    except Exception as e:
        logger.error("Error in sending list", extra={"error": e})
