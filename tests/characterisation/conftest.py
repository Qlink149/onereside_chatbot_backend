"""Characterisation test fixtures.

Mocks OpenAI (SDK boundary), Razorpay client HTTP call, and Gupshup HTTP.
Uses real MongoDB from .env. Chroma semantic_search is stubbed at chroma_utils
(CloudClient hangs on this network; product cases use Mongo get_product_by_id).

NOTE: Chroma stubbed at chroma_utils level for characterisation stability.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import time
import uuid
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable
from unittest.mock import MagicMock, patch

import httpx
import pytest

from tests.db_guard import (
    company,
    enquiries,
    idac,
    messages,
    orders,
    payments,
    product,
)
from onereside_chatbot.main import process_message
import onereside_chatbot.main as main_mod
from onereside_chatbot.utils.env_load import razorpay_webhook_secrete

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VOLATILE = "<VOLATILE>"

_VOLATILE_KEYS = {
    "id",
    "_id",
    "order_id",
    "payment_link_id",
    "payment_id",
    "razorpay_payment_id",
    "payment_short_url",
    "url",
    "short_url",
    "created_at",
    "updated_at",
    "received_at",
    "timestamp",
    "turn_id",
}


def normalize_volatile(obj: Any) -> Any:
    """Replace timestamps, generated IDs, payment URLs with <VOLATILE>."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in _VOLATILE_KEYS:
                out[k] = VOLATILE
            else:
                out[k] = normalize_volatile(v)
        return out
    if isinstance(obj, list):
        return [normalize_volatile(i) for i in obj]
    return obj


def make_openai_message(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        type="message",
        content=[SimpleNamespace(text=text)],
    )


def make_openai_function_call(
    name: str, arguments: dict, call_id: str = "call_test_1"
) -> SimpleNamespace:
    return SimpleNamespace(
        type="function_call",
        name=name,
        arguments=json.dumps(arguments),
        call_id=call_id,
    )


def make_openai_response(*output_items) -> SimpleNamespace:
    resp = SimpleNamespace(output=list(output_items))
    resp.model_dump = lambda: {"output": "mocked"}
    return resp


def build_gupshup_payload(
    phone: str,
    message: dict,
    username: str = "Test User",
) -> dict:
    """Full inbound webhook shape expected by process_message."""
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
                            "contacts": [
                                {"profile": {"name": username}, "wa_id": phone}
                            ],
                        }
                    }
                ]
            }
        ]
    }


def text_message(body: str, phone: str = "000") -> dict:
    return {
        "from": phone,
        "type": "text",
        "text": {"body": body},
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


def nfm_reply_address_message(
    phone: str = "000",
    flow_token: str = "1267811865474716",
    **fields,
) -> dict:
    defaults = {
        "flow_token": flow_token,
        "screen_0_Complete_Address_0": "12 MG Road",
        "screen_0_Pin_Code_1": "560001",
        "screen_0_City_2": "Bengaluru",
        "screen_0_State_3": "Karnataka",
        "screen_0_Country_4": "India",
        "screen_1_First_Name_0": "Ada",
        "screen_1_Last_Name_1": "Lovelace",
        "screen_1_Phone_Number_2": "919876543210",
        "screen_1_Email_3": "ada@example.com",
    }
    defaults.update(fields)
    return {
        "from": phone,
        "type": "interactive",
        "interactive": {
            "type": "nfm_reply",
            "nfm_reply": {
                "name": "flow",
                "response_json": json.dumps(defaults),
            },
        },
    }


def image_message(phone: str = "000") -> dict:
    return {
        "from": phone,
        "type": "image",
        "image": {"id": "media_id_test", "mime_type": "image/jpeg"},
    }


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


@contextmanager
def _boundary_patches(openai_queue: list, gupshup_calls: list, pubsub_events: list, razorpay_calls: list):
    """Apply all external mocks for the duration of one inbound run."""

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

    async def fake_get_openai_responses(**kwargs):
        if not openai_queue:
            return json.dumps({"category": "one_reside"})
        item = openai_queue.pop(0)
        if callable(item):
            item = item()
        if isinstance(item, str):
            return item
        if isinstance(item, SimpleNamespace):
            for out in item.output:
                if out.type == "message" and out.content:
                    return out.content[0].text
            return ""
        return item

    async def fake_responses_create(**kwargs):
        if not openai_queue:
            return make_openai_response(
                make_openai_message(json.dumps({"message": "Hello from OneReside."}))
            )
        item = openai_queue.pop(0)
        if callable(item):
            item = item()
        if isinstance(item, str):
            return make_openai_response(make_openai_message(item))
        return item

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

    def _fake_semantic_search(query, brand_ids=None, exclude_ids=None, n_results=3, **kwargs):
        return []

    def _fake_brand_search(query, n_results=3):
        return []

    import onereside_chatbot.processors.response_manager as rm

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
            patch(
                "onereside_chatbot.utils.pubsub.PubSubManager.publish",
                fake_publish,
            )
        )
        from onereside_chatbot.processors import product_search_agent as psa
        from onereside_chatbot.processors import one_reside_agent as ora

        stub_client = SimpleNamespace(
            responses=SimpleNamespace(create=fake_responses_create)
        )
        stack.enter_context(patch.object(psa, "openai_client", stub_client))
        stack.enter_context(patch.object(ora, "openai_client", stub_client))

        def _fake_create_payment_link(**kwargs):
            return fake_payment_link_create(kwargs)

        stack.enter_context(
            patch(
                "onereside_chatbot.processors.product_checkout.create_payment_link",
                _fake_create_payment_link,
            )
        )
        stack.enter_context(
            patch.object(psa, "semantic_search", _fake_semantic_search)
        )
        stack.enter_context(
            patch.object(psa, "semantic_brand_search", _fake_brand_search)
        )
        yield


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
        "media_url": [
            {"type": "image", "url": "https://example.com/char-priced.jpg"}
        ],
        "listing_type": "product",
        "type": "ready_product",
    }
    product.insert_one(doc)
    yield {k: v for k, v in doc.items() if k != "_id"}
    product.delete_many({"product_id": pid})


@pytest.fixture
def product_without_price(catalog_brand: dict) -> dict:
    pid = f"CHAR-NP-{uuid.uuid4().hex[:6].upper()}"
    doc = {
        "product_id": pid,
        "name": "Characterisation No-Price Lamp",
        "brand_id": catalog_brand["brand_id"],
        "brand_name": catalog_brand["brand_name"],
        "category": "lighting",
        "media_url": [
            {"type": "image", "url": "https://example.com/char-noprice.jpg"}
        ],
        "listing_type": "product",
        "type": "ready_product",
    }
    product.insert_one(doc)
    yield {k: v for k, v in doc.items() if k != "_id"}
    product.delete_many({"product_id": pid})


@pytest.fixture
def product_b(catalog_brand: dict) -> dict:
    pid = f"CHAR-B-{uuid.uuid4().hex[:6].upper()}"
    doc = {
        "product_id": pid,
        "name": "Characterisation Compare Sofa",
        "brand_id": catalog_brand["brand_id"],
        "brand_name": catalog_brand["brand_name"],
        "category": "furniture",
        "price_inr": 22000,
        "media_url": [
            {"type": "image", "url": "https://example.com/char-sofa.jpg"}
        ],
        "listing_type": "product",
        "type": "ready_product",
    }
    product.insert_one(doc)
    yield {k: v for k, v in doc.items() if k != "_id"}
    product.delete_many({"product_id": pid})


@pytest.fixture
def test_brand() -> dict:
    bid = f"char-brand-{uuid.uuid4().hex[:6]}"
    doc = {
        "brand_id": bid,
        "brand_name": "Char Enquiry Brand",
        "brand_description": "Test brand for characterisation",
        "categories_offered": ["furniture"],
        "has_ready_products": True,
        "has_custom_products": False,
        "has_services": False,
    }
    company.insert_one(doc)
    yield {k: v for k, v in doc.items() if k != "_id"}
    company.delete_many({"brand_id": bid})


@pytest.fixture(autouse=True)
def cleanup_mongo(test_phone: str):
    yield
    idac.delete_many({"phone_number": test_phone})
    messages.delete_many({"phone_number": test_phone})
    orders.delete_many({"phone_number": test_phone})
    enquiries.delete_many({"phone_number": test_phone})
    payments.delete_many({"contact": {"$regex": test_phone[-10:]}})


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
def razorpay_calls() -> list:
    return []


@pytest.fixture
def http_boundary_mocks(razorpay_calls):
    """Recorder compatible with CASE 9 asserts (razorpay call list)."""

    class _Rec:
        @property
        def calls(self):
            return razorpay_calls

    return _Rec()


@pytest.fixture
def run_inbound(openai_queue, gupshup_calls, pubsub_events, razorpay_calls, request):
    """Return an async callable that runs process_message under boundary mocks."""

    async def _run(request_data: dict) -> dict | None:
        captured: dict[str, Any] = {"data": None}
        real_save = main_mod.save_to_mongo

        def capturing_save(data):
            captured["data"] = data
            return real_save(data=data)

        with _boundary_patches(openai_queue, gupshup_calls, pubsub_events, razorpay_calls):
            with patch.object(main_mod, "save_to_mongo", side_effect=capturing_save):
                await process_message(request_data)

        if os.environ.get("DUMP_BOT_RESPONSE") == "1" and captured["data"] is not None:
            dump_dir = Path(__file__).parent / "dumps"
            dump_dir.mkdir(exist_ok=True)
            (dump_dir / f"{request.node.name}.json").write_text(
                json.dumps(
                    captured["data"].get("bot_response") or [],
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )

        return captured["data"]

    return _run


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


@pytest.fixture
def seed_order(test_phone: str):
    def _seed(
        payment_link_id: str = "plink_char_test_001",
        **extra,
    ) -> dict:
        doc = {
            "phone_number": test_phone,
            "username": "Test User",
            "product": {"name": "Characterisation Priced Chair", "product_id": "CHAR-X"},
            "amount_inr": 12500,
            "amount_paise": 1250000,
            "payment_link_id": payment_link_id,
            "payment_short_url": "https://rzp.io/i/char-test",
            "razorpay_payment_id": None,
            "payment_status": "pending",
            "order_id": f"ORD-CHAR-{uuid.uuid4().hex[:6].upper()}",
            "created_at": int(time.time()),
            "updated_at": int(time.time()),
            **extra,
        }
        orders.insert_one(doc)
        return doc

    return _seed


def sign_razorpay_body(body: bytes) -> str:
    return hmac.new(
        razorpay_webhook_secrete.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()


@pytest.fixture
def classifier_one_reside(openai_queue):
    openai_queue.append(json.dumps({"category": "one_reside"}))


@pytest.fixture
def classifier_product(openai_queue):
    openai_queue.append(json.dumps({"category": "product"}))


@pytest.fixture
def classifier_agent_request(openai_queue):
    openai_queue.append(json.dumps({"category": "agent_request"}))


@pytest.fixture
def inbound_text_hello() -> Callable[[str], dict]:
    return lambda phone: build_gupshup_payload(phone, text_message("Hello", phone))


@pytest.fixture
def inbound_stop() -> Callable[[str], dict]:
    return lambda phone: build_gupshup_payload(phone, text_message("stop", phone))


@pytest.fixture
def inbound_image() -> Callable[[str], dict]:
    return lambda phone: build_gupshup_payload(phone, image_message(phone))
