"""Phase 4 web identity — no cross-channel merge."""

from __future__ import annotations

import inspect
import time

from tests.db_guard import idac, messages
from onereside_chatbot.web_channel import identity, routes as web_routes
from onereside_chatbot.web_channel.identity import (
    identify,
    link_sessions,
    normalise_phone,
    resolve_user,
    send_otp,
    verify_otp,
)


def test_no_match_sets_phone_in_place(seed_web_user, phone_x, cleanup_identity):
    doc = seed_web_user()
    ref = doc["phone_number"]
    cleanup_identity(ref)

    result = identify(ref, phone=phone_x, intent="enquiry")

    assert result["status"] == "identified"
    assert result["otp_required"] is False
    assert result["canonical_ref"] == ref
    assert result["token"] is None

    updated = idac.find_one({"phone_number": ref})
    assert updated["identifiers"]["phone"] == phone_x
    assert updated.get("merged_into") is None
    assert idac.count_documents({"identifiers.phone": phone_x, "channel": "web"}) == 1


def test_returning_visitor_reconnects(seed_web_user, phone_x, cleanup_identity):
    a = seed_web_user(identifiers_phone=phone_x)
    a_ref = a["phone_number"]
    cleanup_identity(a_ref)
    for i in range(3):
        messages.insert_one(
            {
                "phone_number": a_ref,
                "role": "user",
                "content": f"msg-{i}",
                "timestamp": int(time.time()),
            }
        )

    b = seed_web_user()
    b_ref = b["phone_number"]
    cleanup_identity(b_ref)
    messages.insert_one(
        {
            "phone_number": b_ref,
            "role": "user",
            "content": "from-b",
            "timestamp": int(time.time()),
        }
    )

    result = identify(b_ref, phone=phone_x, intent="enquiry")

    assert result["status"] == "reconnected"
    assert result["canonical_ref"] == a_ref
    assert result["token"]
    assert result["otp_required"] is False

    b_doc = idac.find_one({"phone_number": b_ref})
    assert b_doc["merged_into"] == a_ref
    assert messages.count_documents({"phone_number": b_ref}) == 0
    assert messages.count_documents({"phone_number": a_ref}) == 4


def test_never_matches_whatsapp_user(seed_web_user, phone_x, cleanup_identity):
    wa_ref = phone_x
    cleanup_identity(wa_ref)
    idac.update_one(
        {"phone_number": wa_ref},
        {
            "$set": {
                "username": "WA User",
                "phone_number": wa_ref,
                "service_selected": "",
                "chat_history": [],
                # deliberately no channel field — classic WhatsApp doc
            }
        },
        upsert=True,
    )

    web = seed_web_user()
    web_ref = web["phone_number"]
    cleanup_identity(web_ref)

    result = identify(web_ref, phone=phone_x, intent="enquiry")

    assert result["status"] == "identified"
    assert result["canonical_ref"] == web_ref
    assert result["token"] is None

    wa = idac.find_one({"phone_number": wa_ref})
    assert wa.get("channel") is None
    assert wa.get("merged_into") is None
    assert wa.get("identifiers") is None

    web_doc = idac.find_one({"phone_number": web_ref})
    assert web_doc["identifiers"]["phone"] == phone_x
    assert web_doc.get("merged_into") is None


def test_link_is_idempotent(seed_web_user, cleanup_identity):
    a = seed_web_user(shown_products=[{"product_id": "P1", "name": "One"}])
    b = seed_web_user(shown_products=[{"product_id": "P2", "name": "Two"}])
    a_ref, b_ref = a["phone_number"], b["phone_number"]
    cleanup_identity(a_ref)
    cleanup_identity(b_ref)

    link_sessions(b_ref, a_ref)
    link_sessions(b_ref, a_ref)

    a_doc = idac.find_one({"phone_number": a_ref})
    b_doc = idac.find_one({"phone_number": b_ref})
    assert b_doc["merged_into"] == a_ref
    ids = [p["product_id"] for p in a_doc.get("shown_products", [])]
    assert ids.count("P1") == 1
    assert ids.count("P2") == 1


def test_shown_products_dedupe_by_id(seed_web_user, cleanup_identity):
    a = seed_web_user(
        shown_products=[
            {"product_id": "P1", "name": "One"},
            {"product_id": "P2", "name": "Two"},
        ]
    )
    b = seed_web_user(shown_products=[{"product_id": "P1", "name": "One-dup"}])
    a_ref, b_ref = a["phone_number"], b["phone_number"]
    cleanup_identity(a_ref)
    cleanup_identity(b_ref)

    link_sessions(b_ref, a_ref)

    a_doc = idac.find_one({"phone_number": a_ref})
    ids = [p["product_id"] for p in a_doc["shown_products"]]
    assert ids == ["P1", "P2"]


def test_link_during_active_checkout(seed_web_user, cleanup_identity):
    a = seed_web_user(service_selected="")
    b = seed_web_user(service_selected="product_checkout")
    a_ref, b_ref = a["phone_number"], b["phone_number"]
    cleanup_identity(a_ref)
    cleanup_identity(b_ref)

    link_sessions(b_ref, a_ref)

    a_doc = idac.find_one({"phone_number": a_ref})
    assert a_doc["service_selected"] == "product_checkout"


def test_cyclic_merged_into_does_not_hang(seed_web_user, cleanup_identity):
    a = seed_web_user()
    b = seed_web_user()
    a_ref, b_ref = a["phone_number"], b["phone_number"]
    cleanup_identity(a_ref)
    cleanup_identity(b_ref)
    idac.update_one({"phone_number": a_ref}, {"$set": {"merged_into": b_ref}})
    idac.update_one({"phone_number": b_ref}, {"$set": {"merged_into": a_ref}})

    start = time.time()
    result = resolve_user(a_ref)
    assert time.time() - start < 2
    assert result == a_ref


def test_phone_normalisation():
    canonical = "919876543210"
    assert normalise_phone("+91 98765 43210") == canonical
    assert normalise_phone("09876543210") == canonical
    assert normalise_phone("9876543210") == canonical


def test_otp_functions_exist_but_unused():
    assert callable(send_otp)
    assert callable(verify_otp)
    source = inspect.getsource(web_routes)
    assert "send_otp" not in source
    assert "verify_otp" not in source
    # identity module still exports them for future wiring
    assert hasattr(identity, "send_otp")
    assert hasattr(identity, "verify_otp")
