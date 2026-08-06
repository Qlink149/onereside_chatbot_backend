"""CASE 10 — Razorpay payment_link.paid webhook."""

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from onereside_chatbot.constants import SUPPORT_NOTIFY_NUMBERS
from tests.characterisation.conftest import main_mod, sign_razorpay_body

app = main_mod.app


@pytest.mark.asyncio
async def test_case10_payment_link_paid_updates_order_and_notifies(
    test_phone,
    seed_order,
    gupshup_calls,
):
    payment_link_id = "plink_char_paid_001"
    seed_order(payment_link_id=payment_link_id)

    payload = {
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {
                "entity": {
                    "id": payment_link_id,
                    "status": "paid",
                }
            },
            "payment": {
                "entity": {
                    "id": "pay_char_test_001",
                    "amount": 1250000,
                    "currency": "INR",
                    "status": "captured",
                    "method": "upi",
                    "email": "ada@example.com",
                    "contact": test_phone,
                    "captured": True,
                }
            },
        },
    }
    body = json.dumps(payload).encode("utf-8")
    signature = sign_razorpay_body(body)

    gupshup_calls.clear()

    def fake_httpx_post(url, *args, **kwargs):
        gupshup_calls.append(
            {
                "url": str(url),
                "data": kwargs.get("data"),
                "json": kwargs.get("json"),
                "headers": kwargs.get("headers"),
            }
        )
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"status": "submitted"}
        resp.text = '{"status":"submitted"}'
        return resp

    with patch.object(httpx, "post", fake_httpx_post):
        client = TestClient(app)
        response = client.post(
            "/razorpay/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": signature,
            },
        )

    assert response.status_code == 200

    from tests.db_guard import orders

    order = orders.find_one({"payment_link_id": payment_link_id})
    assert order["payment_status"] == "paid"

    template_urls = [c for c in gupshup_calls if "template/msg" in c["url"]]
    assert len(template_urls) == 1 + len(SUPPORT_NOTIFY_NUMBERS)

    destinations = []
    for c in template_urls:
        data = c.get("data") or {}
        if isinstance(data, dict):
            destinations.append(str(data.get("destination", "")))

    assert destinations.count(test_phone) == 1

    admin_hits = sum(1 for d in destinations if d in SUPPORT_NOTIFY_NUMBERS)
    assert admin_hits == len(SUPPORT_NOTIFY_NUMBERS)
