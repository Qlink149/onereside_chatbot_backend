"""CASES 6–9 — checkout characterisation."""

import pytest

from tests.characterisation.conftest import (
    SAMPLE_ADDRESS,
    build_gupshup_payload,
    button_reply_message,
    nfm_reply_address_message,
)


@pytest.mark.asyncio
async def test_case6_buy_tap_address_on_file_continue_edit(
    test_phone,
    run_inbound,
    seed_user,
    product_with_price,
):
    seed_user(address=SAMPLE_ADDRESS)
    pid = product_with_price["product_id"]

    data = await run_inbound(
        build_gupshup_payload(
            test_phone,
            button_reply_message("Buy", f"buy${pid}", test_phone),
        )
    )

    quickreplies = [i for i in data["bot_response"] if i.get("type") == "quickreply"]
    assert quickreplies

    titles = [o["title"] for o in quickreplies[0]["options"]]
    assert "Continue" in titles

    assert "Edit Address" in titles


@pytest.mark.asyncio
async def test_case7_buy_tap_no_address_sends_flow(
    test_phone,
    run_inbound,
    seed_user,
    product_with_price,
):
    seed_user()
    pid = product_with_price["product_id"]

    data = await run_inbound(
        build_gupshup_payload(
            test_phone,
            button_reply_message("Buy", f"buy${pid}", test_phone),
        )
    )

    assert {"type": "flow", "flow": "address"} in data["bot_response"]


@pytest.mark.asyncio
async def test_case8_nfm_reply_parses_ten_address_fields(
    test_phone,
    run_inbound,
    seed_user,
):
    seed_user()

    data = await run_inbound(
        build_gupshup_payload(
            test_phone,
            nfm_reply_address_message(test_phone),
        )
    )

    from tests.db_guard import idac

    user = idac.find_one({"phone_number": test_phone})
    address = user["address"]

    assert address["address"] == "12 MG Road"
    assert address["pin_code"] == "560001"
    assert address["city"] == "Bengaluru"
    assert address["state"] == "Karnataka"
    assert address["country"] == "India"
    assert address["personal_details"]["first_name"] == "Ada"
    assert address["personal_details"]["last_name"] == "Lovelace"
    assert address["personal_details"]["phone_number"] == "919876543210"
    assert address["personal_details"]["email"] == "ada@example.com"
    assert address["personal_details"]["wa_phone"] == test_phone


@pytest.mark.asyncio
async def test_case9_continue_creates_razorpay_and_cta_url(
    test_phone,
    run_inbound,
    seed_user,
    product_with_price,
    http_boundary_mocks,
):
    from onereside_chatbot.models.service_list import ServiceList

    prod = product_with_price
    # Continue is not a Buy/Enquire shortcut — checkout only runs if prior
    # turn left service_selected as PRODUCT_CHECKOUT (real multi-turn behaviour).
    seed_user(
        address=SAMPLE_ADDRESS,
        selected_product_id=prod,
        service_selected=ServiceList.PRODUCT_CHECKOUT.value,
    )

    data = await run_inbound(
        build_gupshup_payload(
            test_phone,
            button_reply_message("Continue", "address_confirmation", test_phone),
        )
    )

    razorpay_calls = [
        c
        for c in http_boundary_mocks.calls
        if "razorpay.com" in c.get("url", "")
    ]
    assert len(razorpay_calls) >= 1

    assert any(i.get("type") == "cta_url" for i in data["bot_response"])

    from tests.db_guard import orders

    order = orders.find_one({"phone_number": test_phone})
    assert order is not None
    # Prefer address personal phone over WhatsApp ref (SAMPLE_ADDRESS).
    assert order.get("contact_phone") == SAMPLE_ADDRESS["personal_details"]["phone_number"]
