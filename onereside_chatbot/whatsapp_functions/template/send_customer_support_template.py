import httpx

from onereside_chatbot.constants import GUPSHUP_SOURCE
from onereside_chatbot.utils.env_load import (
    gupshup_app_id,
    gupshup_app_name,
    gupshup_token,
)
from onereside_chatbot.utils.logger_config import logger


def send_customer_support_template(phone_number: str, customer_name: str, customer_phone: str):
    """Sends a customer support request notification template to the given phone number.

    Template: customer_support_1
    Params: {{1}} = customer_name, {{2}} = customer_phone
    """
    logger.info(
        "Sending customer support template",
        extra={"phone_number": phone_number, "customer_name": customer_name},
    )

    url = f"https://partner.gupshup.io/partner/app/{gupshup_app_id}/template/msg"

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "content-type": "application/x-www-form-urlencoded",
        "token": gupshup_token,
    }

    data = {
        "source": GUPSHUP_SOURCE,
        "destination": phone_number,
        "src.name": gupshup_app_name,
        "template": (
            '{"id": "c98bfd0d-e04e-4a1d-93be-795fe599b8b1", '
            f'"params": ["*{customer_name}*", "*{customer_phone}*"]'
            '}'
        ),
    }

    try:
        response = httpx.post(url, headers=headers, data=data)
        logger.info(
            "Customer support template sent",
            extra={"phone_number": phone_number, "response": response.json()},
        )
    except Exception as e:
        logger.error(
            "Error sending customer support template",
            extra={"phone_number": phone_number, "error": e},
        )
        raise e
