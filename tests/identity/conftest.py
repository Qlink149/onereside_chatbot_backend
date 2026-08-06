"""Fixtures for web identity tests."""

from __future__ import annotations

import uuid

import pytest

from tests.db_guard import enquiries, idac, messages, orders, payments, rebind_active_test_db


@pytest.fixture
def phone_x() -> str:
    return "919876543210"


@pytest.fixture
def cleanup_identity(phone_x: str):
    """Remove web/WhatsApp docs and related rows touched by identity tests."""
    tracked_refs: list[str] = []

    def track(ref: str):
        tracked_refs.append(ref)
        return ref

    yield track

    rebind_active_test_db()
    refs = list({*tracked_refs})
    for ref in refs:
        idac.delete_many({"phone_number": ref})
        messages.delete_many({"phone_number": ref})
        orders.delete_many({"phone_number": ref})
        enquiries.delete_many({"phone_number": ref})
        payments.delete_many({"contact": ref})
    idac.delete_many({"identifiers.phone": phone_x})
    idac.delete_many({"phone_number": phone_x})


@pytest.fixture
def seed_web_user(cleanup_identity):
    def _seed(
        phone_number: str | None = None,
        *,
        identifiers_phone: str | None = None,
        **extra,
    ) -> dict:
        rebind_active_test_db()
        ref = phone_number or f"web:{uuid.uuid4()}"
        cleanup_identity(ref)
        doc = {
            "username": "Web User",
            "phone_number": ref,
            "service_selected": "",
            "chat_history": [],
            "channel": "web",
            "identifiers": {"phone": identifiers_phone, "email": None},
            "merged_into": None,
            "web_turn_count": 0,
            "shown_products": [],
            "shown_brands": [],
            "pending_needs": [],
            "resolved_needs": [],
            **extra,
        }
        idac.update_one({"phone_number": ref}, {"$set": doc}, upsert=True)
        return doc

    return _seed
