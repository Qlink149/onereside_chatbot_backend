"""CASES 11–12 — enquire characterisation."""

import pytest

from tests.characterisation.conftest import (
    build_gupshup_payload,
    button_reply_message,
)


@pytest.mark.asyncio
async def test_case11_enquire_product_creates_enquiry_and_admin_gupshup(
    test_phone,
    run_inbound,
    seed_user,
    product_without_price,
    gupshup_calls,
):
    seed_user()
    pid = product_without_price["product_id"]
    gupshup_calls.clear()

    data = await run_inbound(
        build_gupshup_payload(
            test_phone,
            button_reply_message("Enquire Now", f"buy${pid}", test_phone),
        )
    )

    from tests.db_guard import enquiries

    enquiry = enquiries.find_one({"phone_number": test_phone})
    assert enquiry is not None

    assert enquiry.get("product", {}).get("product_id") == pid

    admin_template_calls = [
        c for c in gupshup_calls if "template/msg" in c["url"]
    ]
    assert len(admin_template_calls) >= 1


@pytest.mark.asyncio
async def test_case12_enquire_brand_sets_brand_enquiry_type(
    test_phone,
    run_inbound,
    seed_user,
    test_brand,
):
    seed_user()
    bid = test_brand["brand_id"]

    await run_inbound(
        build_gupshup_payload(
            test_phone,
            button_reply_message("Enquire Now", f"enquire${bid}", test_phone),
        )
    )

    from tests.db_guard import enquiries

    enquiry = enquiries.find_one({"phone_number": test_phone})
    assert enquiry is not None

    assert enquiry.get("type") == "brand_enquiry"
