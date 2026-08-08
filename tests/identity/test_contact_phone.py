"""contact_phone resolution for web sessions vs WhatsApp refs."""

from onereside_chatbot.processors.product_checkout import _resolve_contact_phone


def test_web_session_uses_identifiers_phone():
    web_ref = "web:3d2af136-9a22-45f2-b257-f47f3921fd3d"
    profile = {"identifiers": {"phone": "918696979791", "email": None}}
    assert _resolve_contact_phone(web_ref, profile) == "918696979791"


def test_web_session_prefers_address_phone_over_identifiers():
    web_ref = "web:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    profile = {
        "identifiers": {"phone": "918696979791"},
        "address": {
            "personal_details": {"phone_number": "9116914178"},
        },
    }
    assert _resolve_contact_phone(web_ref, profile) == "919116914178"


def test_web_session_anonymous_returns_none():
    web_ref = "web:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    profile = {"identifiers": {"phone": None, "email": None}}
    assert _resolve_contact_phone(web_ref, profile) is None


def test_whatsapp_ref_used_when_no_identifiers():
    assert _resolve_contact_phone("919876543210", {}) == "919876543210"
