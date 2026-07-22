import httpx

from onereside_chatbot.utils.env_load import (
    gupshup_app_id,
    gupshup_token
)
from onereside_chatbot.utils.logger_config import logger


def send_address_flow(phone_number: str):
    """Sends a address flow to a phone number."""
    logger.info(
        "Sending address flow to phone number",
        extra={"phone_number": phone_number},
    )
    url = f"https://partner.gupshup.io/partner/app/{gupshup_app_id}/v3/message"
    headers = {
        "Authorization": f"{gupshup_token}",
        "Content-Type": "application/json",
    }
    data = {
        "recipient_type": "individual",
        "messaging_product": "whatsapp",
        "to": f"{phone_number}",
        "type": "interactive",
        "interactive": {
            "type": "flow",
            "header": {"type": "text", "text": "Checkout Address"},
            "body": {
                "text": "Please set your address."
            },
            "footer": {"text": "Managed by OneReside."},
            "action": {
                "name": "flow",
                "parameters": {
                    "flow_token": "1267811865474716",
                    "flow_id": "1267811865474716",
                    "flow_message_version": "3",
                    "flow_action": "navigate",
                    "flow_cta": "Fill Address",
                    "flow_action_payload": {
                        "screen": "RECOMMEND",
                        "data": {
                            "Full name": "Vaibhav Verma",
                            "Brand name": "Qlink",
                            "Email": "vaibhav@gmail.com",
                            "Whatsapp Number": "+919999999999",
                        },
                    },
                },
            },
        },
    }

    try:
        response = httpx.post(url, headers=headers, json=data)
        logger.info("Response", extra={"response": response.json()})
        return response.json()
    except Exception as e:
        logger.error("Error in sending spot booking flow", extra={"error": e})
        raise e
