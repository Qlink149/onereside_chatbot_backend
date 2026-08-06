"""Resolve the correct Sender for a user_ref."""

from onereside_chatbot.channels.base import Sender
from onereside_chatbot.channels.web import WebSender
from onereside_chatbot.channels.whatsapp import WhatsAppSender


def get_sender(user_ref: str) -> Sender:
    if user_ref.startswith("web:"):
        return WebSender(user_ref)
    return WhatsAppSender(user_ref)
