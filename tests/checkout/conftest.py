"""Checkout suite fixtures — isolated Mongo (OneReside_test), never prod."""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import time
import uuid
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from tests.db_guard import company, idac, messages, orders, product
from onereside_chatbot.main import process_message
import onereside_chatbot.main as main_mod
from onereside_chatbot.utils.env_load import razorpay_webhook_secrete

SAMPLE_ADDRESS = {
    "address": "12 MG Road",
    "pin_code": "560001",
    "city": "Bengaluru",
    "state": "Karnataka",
    "country": "India",
    "personal_details": {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "phone_number": "919876543210",
        "email": "ada@example.com",
        "wa_phone": "",
    },
}


def build_gupshup_payload(phone: str, message: dict, username: str = "Test User") -> dict:
    msg = copy.deepcopy(message)
    msg.setdefault("from", phone)
    msg.setdefault("id", f"wamid.test.{uuid.uuid4().hex[:12]}")
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [msg],
                            "contacts": [{"profile": {"name": username}, "wa_id": phone}],
                        }
                    }
                ]
            }
        ]
    }


def button_reply_message(title: str, msgid: str, phone: str = "000") -> dict:
    return {
        "from": phone,
        "type": "interactive",
        "interactive": {
            "type": "button_reply",
            "button_reply": {
                "title": title,
                "id": json.dumps({"msgid": msgid}),
            },
        },
    }


def sign_razorpay_body(body: bytes) -> str:
    return hmac.new(
        razorpay_webhook_secrete.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()


@pytest.fixture
def test_phone() -> str:
    return f"9199{uuid.uuid4().hex[:8]}"


@pytest.fixture
def catalog_brand() -> dict:
    bid = f"char-test-brand-{uuid.uuid4().hex[:6]}"
    doc = {
        "brand_id": bid,
        "brand_name": "Char Test Brand",
        "brand_description": "Characterisation catalog brand",
        "categories_offered": ["furniture", "lighting"],
        "has_ready_products": True,
        "has_custom_products": False,
        "has_services": False,
    }
    company.insert_one(doc)
    yield {k: v for k, v in doc.items() if k != "_id"}
    company.delete_many({"brand_id": bid})


@pytest.fixture
def product_with_price(catalog_brand: dict) -> dict:
    pid = f"CHAR-WP-{uuid.uuid4().hex[:6].upper()}"
    doc = {
        "product_id": pid,
        "name": "Characterisation Priced Chair",
        "brand_id": catalog_brand["brand_id"],
        "brand_name": catalog_brand["brand_name"],
        "category": "furniture",
        "price_inr": 12500,
        "media_url": [{"type": "image", "url": "https://example.com/char-priced.jpg"}],
        "listing_type": "product",
        "type": "ready_product",
    }
    product.insert_one(doc)
    yield {k: v for k, v in doc.items() if k != "_id"}
    product.delete_many({"product_id": pid})


@pytest.fixture(autouse=True)
def cleanup_mongo(test_phone: str):
    yield
    idac.delete_many({"phone_number": test_phone})
    messages.delete_many({"phone_number": test_phone})
    orders.delete_many({"phone_number": test_phone})


@pytest.fixture
def razorpay_calls() -> list:
    return []


@pytest.fixture
def gupshup_calls() -> list:
    return []


@pytest.fixture
def pubsub_events() -> list:
    return []


@pytest.fixture
def openai_queue() -> list:
    return []


@pytest.fixture
def http_boundary_mocks(razorpay_calls):
    class _Rec:
        @property
        def calls(self):
            return razorpay_calls

    return _Rec()


@pytest.fixture
def seed_user(test_phone: str):
    def _seed(**extra) -> dict:
        doc = {
            "phone_number": test_phone,
            "username": "Test User",
            "service_selected": "",
            "chat_history": [],
            **extra,
        }
        idac.insert_one(doc)
        return doc

    return _seed


@contextmanager
def _boundary_patches(openai_queue, gupshup_calls, pubsub_events, razorpay_calls):
    def fake_httpx_post(url, *args, **kwargs):
        gupshup_calls.append(
            {"url": str(url), "data": kwargs.get("data"), "json": kwargs.get("json")}
        )
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"status": "submitted"}
        resp.text = '{"status":"submitted"}'
        return resp

    async def fake_get_openai_responses(**kwargs):
        return json.dumps({"category": "one_reside"})

    async def fake_responses_create(**kwargs):
        return SimpleNamespace(
            output=[SimpleNamespace(type="message", content=[SimpleNamespace(text="ok")])],
            model_dump=lambda: {},
        )

    async def fake_publish(self, phone_number, event):
        pubsub_events.append({"phone_number": phone_number, "event": event})

    def fake_payment_link_create(payload):
        razorpay_calls.append(
            {"url": "https://api.razorpay.com/v1/payment_links", "payload": payload}
        )
        return {
            "id": "plink_char_test_001",
            "short_url": "https://rzp.io/i/char-test",
            "status": "created",
            "amount": payload.get("amount", 0),
        }

    import onereside_chatbot.processors.response_manager as rm
    from onereside_chatbot.processors import one_reside_agent as ora
    from onereside_chatbot.processors import product_search_agent as psa

    with ExitStack() as stack:
        stack.enter_context(patch.object(httpx, "post", fake_httpx_post))
        stack.enter_context(patch.object(time, "sleep", lambda *_a, **_k: None))
        stack.enter_context(patch.object(rm.time, "sleep", lambda *_a, **_k: None))
        stack.enter_context(
            patch(
                "onereside_chatbot.processors.classifier.get_openai_responses",
                fake_get_openai_responses,
            )
        )
        stack.enter_context(
            patch("onereside_chatbot.utils.pubsub.PubSubManager.publish", fake_publish)
        )
        stub_client = SimpleNamespace(responses=SimpleNamespace(create=fake_responses_create))
        stack.enter_context(patch.object(psa, "openai_client", stub_client))
        stack.enter_context(patch.object(ora, "openai_client", stub_client))
        stack.enter_context(
            patch(
                "onereside_chatbot.processors.product_checkout.create_payment_link",
                lambda **kwargs: fake_payment_link_create(kwargs),
            )
        )
        stack.enter_context(patch.object(psa, "semantic_search", lambda *a, **k: []))
        stack.enter_context(patch.object(psa, "semantic_brand_search", lambda *a, **k: []))
        yield


@pytest.fixture
def run_inbound(openai_queue, gupshup_calls, pubsub_events, razorpay_calls):
    async def _run(request_data: dict) -> dict | None:
        captured: dict[str, Any] = {"data": None}
        real_save = main_mod.save_to_mongo

        def capturing_save(data):
            captured["data"] = data
            return real_save(data=data)

        with _boundary_patches(openai_queue, gupshup_calls, pubsub_events, razorpay_calls):
            with patch.object(main_mod, "save_to_mongo", side_effect=capturing_save):
                await process_message(request_data)
        return captured["data"]

    return _run
