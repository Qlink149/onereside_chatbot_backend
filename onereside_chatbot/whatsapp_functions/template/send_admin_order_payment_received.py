import httpx

from onereside_chatbot.constants import GUPSHUP_SOURCE
from onereside_chatbot.utils.env_load import (
    gupshup_app_id,
    gupshup_app_name,
    gupshup_token,
)
from onereside_chatbot.utils.logger_config import logger


def send_admin_order_payment_received(admin_phone: str, order_id: str, customer_name: str, customer_phone: str):
    """Notifies admin that an order payment has been verified."""
    logger.info(
        "Sending order payment received notification to admin",
        extra={"admin_phone": admin_phone, "order_id": order_id},
    )
    destination = f"{admin_phone}"
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
        "template": f'{{"id": "5c640a4c-3de4-4aa0-b633-02508bf798c5", "params": ["{order_id}", "{customer_name}", "{customer_phone}"]}}',
    }

    try:
        response = httpx.post(url, headers=headers, data=data)
        logger.info(
            "Response",
            extra={
                "admin_phone": admin_phone,
                "response": response.json(),
            },
        )
    except Exception as e:
        logger.error(
            "Error in sending admin order payment notification",
            extra={"admin_phone": admin_phone, "error": e},
        )
        raise e
