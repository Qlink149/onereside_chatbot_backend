import httpx

from onereside_chatbot.constants import GUPSHUP_SOURCE
from onereside_chatbot.utils.env_load import (
    gupshup_app_id,
    gupshup_app_name,
    gupshup_token,
)
from onereside_chatbot.utils.logger_config import logger


def send_user_order_payment_failed(phone_number: str, amount: str, product_name: str, order_id: str):
    """Notifies user that their order payment failed."""
    logger.info(
        "Sending order payment failed message to user",
        extra={"phone_number": phone_number, "order_id": order_id},
    )
    destination = f"{phone_number}"
    url = f"https://partner.gupshup.io/partner/app/{gupshup_app_id}/template/msg"

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "content-type": "application/x-www-form-urlencoded",
        "token": gupshup_token,
    }

    data = {
        "source": GUPSHUP_SOURCE,
        "destination": destination,
        "src.name": gupshup_app_name,
        "template": f'{{"id": "7bf239cc-2aa5-4c41-aff1-7996c620a044", "params": ["{amount}", "{product_name}", "{order_id}"]}}',
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
    except Exception as e:
        logger.error(
            "Error in sending order payment failed message",
            extra={"phone_number": phone_number, "error": e},
        )
        raise e
