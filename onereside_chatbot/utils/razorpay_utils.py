from razorpay import Client
from onereside_chatbot.utils.env_load import (
    razorpay_app_id, razorpay_app_secrete
)
from onereside_chatbot.utils.logger_config import logger
from onereside_chatbot.constants import RAZORPAY_REDIRECT

APP_ID = razorpay_app_id
APP_SECRETE = razorpay_app_secrete



razorpay_client = Client(auth=(APP_ID, APP_SECRETE))


def create_payment_link(
    amount: int,
    phone: str,
    name: str = "",
    email: str = "",
    description: str = "",
    currency: str = "INR",
    callback_url: str = RAZORPAY_REDIRECT,
) -> dict:
    """
    Create a Razorpay payment link.

    Args:
        amount: Amount in paise (e.g. 50000 = ₹500).
        phone: Customer phone number (with country code, e.g. '919876543210').
        name: Customer name.
        email: Customer email.
        description: Short description shown on the payment page.
        currency: Currency code (default INR).
        callback_url: URL to redirect after payment.

    Returns:
        Razorpay payment link response dict (includes 'short_url').
    """
    try:
        payload = {
            "amount": amount,
            "currency": currency,
            "description": description,
            "customer": {
                "name": name,
                "email": email,
                "contact": phone,
            },
            "notify": {
                "sms": False,
                "email": True,
            },
            "reminder_enable": False,
        }

        if callback_url:
            payload["callback_url"] = callback_url
            payload["callback_method"] = "get"

        response = razorpay_client.payment_link.create(payload)
        logger.info(
            "Razorpay payment link created",
            extra={"payment_link_id": response.get("id"), "short_url": response.get("short_url")},
        )
        return response

    except Exception as e:
        logger.exception("Failed to create Razorpay payment link.", extra={"exception": e})
        raise e
