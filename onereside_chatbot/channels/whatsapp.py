"""WhatsApp channel sender — pure delegation to existing Gupshup send_* functions."""

from onereside_chatbot.whatsapp_functions.cta.send_cta import send_cta_url
from onereside_chatbot.whatsapp_functions.flow.send_address_flow import send_address_flow
from onereside_chatbot.whatsapp_functions.flow.send_site_visit import send_site_visit_flow
from onereside_chatbot.whatsapp_functions.list.send_service_list import send_service_list
from onereside_chatbot.whatsapp_functions.media.send_audio_message import send_audio_message
from onereside_chatbot.whatsapp_functions.media.send_document_message import send_file_message
from onereside_chatbot.whatsapp_functions.media.send_image_message import send_image_message
from onereside_chatbot.whatsapp_functions.quick_reply.send_quick_reply import send_quickreply
from onereside_chatbot.whatsapp_functions.send_text_message import send_text_message
from onereside_chatbot.whatsapp_functions.template.send_admin_order_payment_received import (
    send_admin_order_payment_received,
)
from onereside_chatbot.whatsapp_functions.template.send_user_order_payment_failed import (
    send_user_order_payment_failed,
)
from onereside_chatbot.whatsapp_functions.template.send_user_order_payment_received import (
    send_user_order_payment_received,
)


class WhatsAppSender:
    """Delegates each message type to the corresponding existing send_* function."""

    def __init__(self, user_ref: str):
        self.user_ref = user_ref

    def send_text(self, phone_number: str, bot_response: dict):
        return send_text_message(phone_number=phone_number, bot_response=bot_response)

    def send_quickreply(self, phone_number, bot_response):
        return send_quickreply(phone_number=phone_number, bot_response=bot_response)

    def send_skip(self, phone_number, bot_response):
        return {"status": "submitted"}

    def send_cta_url(self, phone_number, bot_response):
        return send_cta_url(phone_number=phone_number, bot_response=bot_response)

    def send_list(self, phone_number, bot_response: dict):
        list_name = bot_response["list"]
        if list_name == "service_list":
            return send_service_list(phone_number=phone_number)
        raise ValueError(f"Unknown list: {list_name}")

    def send_flow(self, phone_number, bot_response: dict):
        flow_name = bot_response["flow"]
        if flow_name == "site_visit":
            return send_site_visit_flow(phone_number=phone_number)
        if flow_name == "address":
            return send_address_flow(phone_number=phone_number)
        raise ValueError(f"Unknown flow: {flow_name}")

    def send_template(self, phone_number, bot_response: dict):
        template_name = bot_response["template"]
        if template_name == "user_order_payment_failed":
            return send_user_order_payment_failed(
                phone_number=phone_number,
                amount=bot_response["amount"],
                product_name=bot_response["product_name"],
                order_id=bot_response["order_id"],
            )
        if template_name == "user_order_payment_received":
            return send_user_order_payment_received(
                phone_number=phone_number,
                amount=bot_response["amount"],
                product_name=bot_response["product_name"],
                order_id=bot_response["order_id"],
            )
        if template_name == "admin_order_payment_received":
            return send_admin_order_payment_received(
                admin_phone=phone_number,
                order_id=bot_response["order_id"],
                customer_name=bot_response["customer_name"],
                customer_phone=bot_response["customer_phone"],
            )
        raise ValueError(f"Unknown template: {template_name}")

    def send_media(self, phone_number, bot_response: dict):
        media_type = bot_response["media_type"]
        if media_type == "image":
            return send_image_message(phone_number=phone_number, bot_response=bot_response)
        if media_type == "document":
            return send_file_message(phone_number=phone_number, bot_response=bot_response)
        if media_type == "audio":
            return send_audio_message(phone_number=phone_number, bot_response=bot_response)
        raise ValueError(f"Unknown media type: {media_type}")

    def send_status(self, stage: str, detail: str) -> None:
        return None
