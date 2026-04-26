import httpx

from onereside_chatbot.constants import GUPSHUP_SOURCE
from onereside_chatbot.utils.env_load import (
    gupshup_app_id,
    gupshup_app_name,
    gupshup_token,
)
from onereside_chatbot.utils.logger_config import logger


def send_product_enquiry_template(phone_number: str, product_name: str, customer_name: str, customer_phone: str):
    """Sends a product enquiry notification template to the given phone number.

    Template: product_enq_2
    Params: {{1}} = product_name, {{2}} = customer_name, {{3}} = customer_phone
    """
    logger.info(
        "Sending product enquiry template",
        extra={"phone_number": phone_number, "product_name": product_name},
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
            '{"id": "f252c353-e04a-40a5-8863-87d72cc6e26b", '
            f'"params": ["*{product_name}*", "*{customer_name}*", "*{customer_phone}*"]'
            '}'
        ),
    }

    try:
        response = httpx.post(url, headers=headers, data=data)
        logger.info(
            "Product enquiry template sent",
            extra={"phone_number": phone_number, "response": response.json()},
        )
    except Exception as e:
        logger.error(
            "Error sending product enquiry template",
            extra={"phone_number": phone_number, "error": e},
        )
        raise e
