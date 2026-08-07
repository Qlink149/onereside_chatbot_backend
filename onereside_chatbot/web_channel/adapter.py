"""Map web widget payloads to WhatsApp-shaped inbound messages for the pipeline."""

from __future__ import annotations

import json
import time
import uuid

from onereside_chatbot.models.enums import FLowId
from onereside_chatbot.orchestration.turn import Turn

# Prompt example that routes to agent_request via the classifier.
AGENT_REQUEST_TEXT = "Can I talk to someone?"


def _button_reply(user_ref: str, title: str, msgid: str) -> dict:
    return {
        "from": user_ref,
        "id": f"webamid.{uuid.uuid4().hex[:12]}",
        "type": "interactive",
        "interactive": {
            "type": "button_reply",
            "button_reply": {
                "title": title,
                "id": json.dumps({"msgid": msgid}),
            },
        },
    }


def _text_message(user_ref: str, body: str) -> dict:
    return {
        "from": user_ref,
        "id": f"webamid.{uuid.uuid4().hex[:12]}",
        "type": "text",
        "text": {"body": body},
    }


def build_inbound(user_ref: str, payload: dict) -> dict:
    """Return the exact data['messages'] shape the pipeline consumes."""
    if "text" in payload and payload.get("action") is None:
        return _text_message(user_ref, str(payload["text"]))

    action = payload.get("action")
    if action == "buy":
        product_id = payload.get("product_id")
        if not product_id:
            raise ValueError("buy requires product_id")
        return _button_reply(user_ref, "Buy", f"buy${product_id}")

    if action == "enquire_product":
        # Code/CASE 11: msgid is buy$ even for Enquire Now on products.
        product_id = payload.get("product_id")
        if not product_id:
            raise ValueError("enquire_product requires product_id")
        return _button_reply(user_ref, "Enquire Now", f"buy${product_id}")

    if action == "enquire_brand":
        brand_id = payload.get("brand_id")
        if not brand_id:
            raise ValueError("enquire_brand requires brand_id")
        return _button_reply(user_ref, "Enquire Now", f"enquire${brand_id}")

    if action == "confirm_address":
        return _button_reply(user_ref, "Continue", "address_confirmation")

    if action == "edit_address":
        return _button_reply(user_ref, "Edit Address", "address_confirmation")

    if action == "submit_address":
        fields = payload.get("fields") or {}
        flow_data = {
            "flow_token": FLowId.CHECKOUT_ADDRESS.value,
            "screen_0_Complete_Address_0": fields.get(
                "flat", fields.get("address", fields.get("complete_address", ""))
            ),
            "screen_0_Pin_Code_1": fields.get("pincode", fields.get("pin_code", "")),
            "screen_0_City_2": fields.get("city", ""),
            "screen_0_State_3": fields.get("state", ""),
            "screen_0_Country_4": fields.get("country", "India"),
            "screen_1_First_Name_0": fields.get(
                "first_name", fields.get("name", "").split(" ")[0] if fields.get("name") else ""
            ),
            "screen_1_Last_Name_1": fields.get(
                "last_name",
                " ".join(fields.get("name", "").split(" ")[1:]) if fields.get("name") else "",
            ),
            "screen_1_Phone_Number_2": fields.get("phone", fields.get("phone_number", "")),
            "screen_1_Email_3": fields.get("email", ""),
        }
        # Allow direct screen_* keys from clients that already speak the flow dialect.
        for key, value in fields.items():
            if key.startswith("screen_") or key == "flow_token":
                flow_data[key] = value
        return {
            "from": user_ref,
            "id": f"webamid.{uuid.uuid4().hex[:12]}",
            "type": "interactive",
            "interactive": {
                "type": "nfm_reply",
                "nfm_reply": {
                    "name": "flow",
                    "response_json": json.dumps(flow_data),
                },
            },
        }

    if action == "agent_request":
        return _text_message(user_ref, AGENT_REQUEST_TEXT)

    if action == "cancel":
        return _button_reply(user_ref, "cancel purchase", "cancel_purchase")

    if action == "show_similar":
        return _button_reply(user_ref, "Show similar", "show_similar_oos")

    raise ValueError(f"Unknown action: {payload}")


def build_turn(user_ref: str, display_name: str, payload: dict) -> Turn:
    """Build a web-channel Turn from a widget payload."""
    return Turn(
        channel="web",
        user_ref=user_ref,
        session_id=user_ref,
        messages=build_inbound(user_ref, payload),
        display_name=display_name or "Web User",
        received_at=int(time.time()),
    )
