"""Phase 6 checkout tests — stock check and webhook hardening."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from tests.db_guard import orders, product
from onereside_chatbot.models.service_list import ServiceList
import onereside_chatbot.main as main_mod
from tests.checkout.conftest import (
    SAMPLE_ADDRESS,
    build_gupshup_payload,
    button_reply_message,
    sign_razorpay_body,
)

app = main_mod.app


async def _continue_checkout(run_inbound, test_phone, seed_user, prod):
    seed_user(
        address=SAMPLE_ADDRESS,
        selected_product_id=prod,
        service_selected=ServiceList.PRODUCT_CHECKOUT.value,
    )
    return await run_inbound(
        build_gupshup_payload(
            test_phone,
            button_reply_message("Continue", "address_confirmation", test_phone),
        )
    )


@pytest.mark.asyncio
async def test_out_of_stock_blocks_payment_link(
    test_phone,
    run_inbound,
    seed_user,
    product_with_price,
    http_boundary_mocks,
):
    product.update_one(
        {"product_id": product_with_price["product_id"]},
        {"$set": {"inventory_status": "out_of_stock"}},
    )
    prod = {**product_with_price, "inventory_status": "out_of_stock"}

    data = await _continue_checkout(run_inbound, test_phone, seed_user, prod)

    razorpay_calls = [
        c for c in http_boundary_mocks.calls if "razorpay.com" in c.get("url", "")
    ]
    assert razorpay_calls == []
    assert orders.count_documents({"phone_number": test_phone}) == 0

    qrs = [i for i in (data.get("bot_response") or []) if i.get("type") == "quickreply"]
    assert qrs
    assert "no longer available" in qrs[0]["text"]
    assert qrs[0]["msgid"] == "show_similar_oos"
    assert any(o.get("title") == "Show similar" for o in qrs[0]["options"])


@pytest.mark.asyncio
async def test_in_stock_creates_payment_link(
    test_phone,
    run_inbound,
    seed_user,
    product_with_price,
    http_boundary_mocks,
):
    product.update_one(
        {"product_id": product_with_price["product_id"]},
        {"$set": {"inventory_status": "in_stock"}},
    )
    prod = {**product_with_price, "inventory_status": "in_stock"}

    data = await _continue_checkout(run_inbound, test_phone, seed_user, prod)

    razorpay_calls = [
        c for c in http_boundary_mocks.calls if "razorpay.com" in c.get("url", "")
    ]
    assert len(razorpay_calls) >= 1
    cta = [i for i in data["bot_response"] if i.get("type") == "cta_url"]
    assert cta
    assert cta[0].get("order_id")
    assert orders.count_documents({"phone_number": test_phone}) == 1


@pytest.mark.asyncio
async def test_absent_inventory_field_proceeds(
    test_phone,
    run_inbound,
    seed_user,
    product_with_price,
    http_boundary_mocks,
):
    product.update_one(
        {"product_id": product_with_price["product_id"]},
        {"$unset": {"inventory_status": ""}},
    )
    prod = {k: v for k, v in product_with_price.items() if k != "inventory_status"}

    data = await _continue_checkout(run_inbound, test_phone, seed_user, prod)

    razorpay_calls = [
        c for c in http_boundary_mocks.calls if "razorpay.com" in c.get("url", "")
    ]
    assert len(razorpay_calls) >= 1
    assert any(i.get("type") == "cta_url" for i in data["bot_response"])


@pytest.mark.asyncio
async def test_payment_failed_without_payment_link_entity():
    payload = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_orphan_fail_001",
                    "status": "failed",
                    "amount": 10000,
                }
            }
        },
    }
    body = json.dumps(payload).encode("utf-8")
    sig = sign_razorpay_body(body)

    client = TestClient(app)
    res = client.post(
        "/razorpay/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": sig,
        },
    )

    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_stock_check_applies_to_whatsapp_channel(
    test_phone,
    run_inbound,
    seed_user,
    product_with_price,
    http_boundary_mocks,
):
    """Gupshup inbound has no channel=web — same stock block must apply."""
    product.update_one(
        {"product_id": product_with_price["product_id"]},
        {"$set": {"inventory_status": "out_of_stock"}},
    )
    prod = {**product_with_price, "inventory_status": "out_of_stock"}

    data = await _continue_checkout(run_inbound, test_phone, seed_user, prod)

    razorpay_calls = [
        c for c in http_boundary_mocks.calls if "razorpay.com" in c.get("url", "")
    ]
    assert razorpay_calls == []
    assert any(
        i.get("msgid") == "show_similar_oos" for i in (data.get("bot_response") or [])
    )
