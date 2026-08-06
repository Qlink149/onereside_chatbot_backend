"""Send OTP verification template via Gupshup (unused in V1 identify flow)."""

import json

import httpx

from onereside_chatbot.constants import GUPSHUP_SOURCE
from onereside_chatbot.utils.env_load import (
    gupshup_app_id,
    gupshup_app_name,
    gupshup_token,
)
from onereside_chatbot.utils.logger_config import logger

# Placeholder template id — replace when a production OTP template is registered.
_OTP_TEMPLATE_ID = "00000000-0000-0000-0000-000000000000"


def send_otp_template(phone_number: str, otp_code: str):
    """Send a one-time-password template to ``phone_number`` (canonical digits)."""
    logger.info(
        "Sending OTP template",
        extra={"phone_number": phone_number},
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
        "template": json.dumps({"id": _OTP_TEMPLATE_ID, "params": [otp_code]}),
    }
    try:
        response = httpx.post(url, headers=headers, data=data)
        logger.info(
            "OTP template sent",
            extra={"phone_number": phone_number, "status_code": response.status_code},
        )
        return response
    except Exception as e:
        logger.error(
            "Error sending OTP template",
            extra={"phone_number": phone_number, "error": e},
        )
        raise e
