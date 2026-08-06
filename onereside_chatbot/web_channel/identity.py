"""Web-channel identity: anonymous sessions, phone identify, web-to-web linking.

WhatsApp and web users are NEVER merged. Identify only matches other web docs.
"""

from __future__ import annotations

import random
import re
import time
import uuid

from onereside_chatbot.database.collections import (
    admin_logs,
    enquiries,
    idac,
    messages,
    orders,
    payments,
)
from onereside_chatbot.routes.system_sub_routes.auth import create_web_token
from onereside_chatbot.utils.logger_config import logger
from onereside_chatbot.utils.pubsub import PubSubManager
from onereside_chatbot.whatsapp_functions.template.send_otp_template import send_otp_template

_OTP_TTL_SECONDS = 600
_OTP_MAX_ATTEMPTS = 3
_RESOLVE_MAX_HOPS = 10


def create_anonymous(brand_id: str | None = None, bound_origin: str | None = None) -> dict:
    """Create an anonymous web user doc and mint a JWT.

    Returns ``{session_id, token}``.
    """
    user_ref = f"web:{uuid.uuid4()}"
    # phone_number holds "web:<uuid>" for web users by design so downstream
    # code that keys on phone_number needs no channel-specific branches.
    profile: dict = {
        "username": "Web User",
        "phone_number": user_ref,
        "service_selected": "",
        "chat_history": [],
        "channel": "web",
        "identifiers": {"phone": None, "email": None},
        "merged_into": None,
        "web_turn_count": 0,
    }
    if brand_id:
        profile["current_brand"] = brand_id
        profile["requested_brand"] = None

    idac.update_one(
        {"phone_number": user_ref},
        {"$set": profile},
        upsert=True,
    )
    token = create_web_token(user_ref, bound_origin=bound_origin)
    return {"session_id": user_ref, "token": token}


def normalise_phone(raw: str) -> str:
    """Convert typed input to WhatsApp storage form: digits only, 91-prefixed.

    Examples of canonical form: ``919876543210`` (no ``+``, no spaces).
    """
    if raw is None:
        raise ValueError("phone is required")
    digits = re.sub(r"[^\d]", "", str(raw).strip())
    if digits.startswith("0"):
        digits = digits.lstrip("0")
    if len(digits) == 10:
        digits = "91" + digits
    if not digits.startswith("91") or len(digits) < 12:
        # Still return cleaned digits; callers may validate length.
        pass
    return digits


def resolve_user(user_ref: str) -> str:
    """Follow ``merged_into`` to the canonical ref (max 10 hops). Never raises."""
    if not user_ref:
        return user_ref
    seen: set[str] = set()
    current = user_ref
    for _ in range(_RESOLVE_MAX_HOPS):
        if current in seen:
            logger.error(
                "Cyclic merged_into detected",
                extra={"user_ref": user_ref, "stuck_at": current},
            )
            return user_ref
        seen.add(current)
        doc = idac.find_one({"phone_number": current}, {"merged_into": 1})
        if not doc:
            return current
        nxt = doc.get("merged_into")
        if not nxt:
            return current
        current = nxt
    logger.error(
        "merged_into hop limit exceeded",
        extra={"user_ref": user_ref, "last": current},
    )
    return user_ref


def _dedupe_by_key(existing: list, incoming: list, key: str) -> list:
    """Merge object lists, keeping first occurrence of each key value."""
    out: list = list(existing or [])
    seen = {item.get(key) for item in out if isinstance(item, dict) and item.get(key)}
    for item in incoming or []:
        if not isinstance(item, dict):
            if item not in out:
                out.append(item)
            continue
        kid = item.get(key)
        if kid and kid in seen:
            continue
        if kid:
            seen.add(kid)
        out.append(item)
    return out


def _dedupe_needs(existing: list, incoming: list) -> list:
    """Merge need lists (strings or objects) without exact duplicates."""
    out = list(existing or [])
    for item in incoming or []:
        if item not in out:
            out.append(item)
    return out


def _publish_reconnected(from_ref: str, to_ref: str) -> None:
    pubsub = PubSubManager()
    event = {"type": "session_reconnected", "canonical_ref": to_ref}
    for queue in pubsub._subscribers.get(from_ref, []):
        try:
            queue.put_nowait(event)
        except Exception:
            logger.exception("Failed to publish session_reconnected", extra={"from_ref": from_ref})


def link_sessions(from_ref: str, to_ref: str) -> None:
    """Repoint web session ``from_ref`` onto canonical web user ``to_ref``.

    Idempotent: if ``from_ref`` already has ``merged_into``, returns immediately.
    Both docs must have ``channel == "web"``.
    """
    if from_ref == to_ref:
        return

    source = idac.find_one({"phone_number": from_ref})
    target = idac.find_one({"phone_number": to_ref})
    if not source or not target:
        raise ValueError("link_sessions requires both user docs to exist")
    if source.get("channel") != "web" or target.get("channel") != "web":
        raise AssertionError("link_sessions is web-to-web only")

    if source.get("merged_into"):
        return

    # 1. Repoint dependent collections
    messages.update_many({"phone_number": from_ref}, {"$set": {"phone_number": to_ref}})
    orders.update_many({"phone_number": from_ref}, {"$set": {"phone_number": to_ref}})
    enquiries.update_many({"phone_number": from_ref}, {"$set": {"phone_number": to_ref}})
    payments.update_many({"contact": from_ref}, {"$set": {"contact": to_ref}})
    admin_logs.update_many(
        {"details.phone_number": from_ref},
        {"$set": {"details.phone_number": to_ref}},
    )

    # 2. Carry state onto target only when empty / merge list fields
    target_updates: dict = {}
    if not target.get("service_selected") and source.get("service_selected"):
        target_updates["service_selected"] = source["service_selected"]
    if not target.get("current_brand") and source.get("current_brand"):
        target_updates["current_brand"] = source["current_brand"]

    target_updates["shown_products"] = _dedupe_by_key(
        target.get("shown_products") or [],
        source.get("shown_products") or [],
        "product_id",
    )
    target_updates["shown_brands"] = _dedupe_by_key(
        target.get("shown_brands") or [],
        source.get("shown_brands") or [],
        "brand_id",
    )
    target_updates["pending_needs"] = _dedupe_needs(
        target.get("pending_needs") or [],
        source.get("pending_needs") or [],
    )
    target_updates["resolved_needs"] = _dedupe_needs(
        target.get("resolved_needs") or [],
        source.get("resolved_needs") or [],
    )

    if target_updates:
        idac.update_one({"phone_number": to_ref}, {"$set": target_updates})

    # 3. Mark source as merged (do not delete)
    idac.update_one(
        {"phone_number": from_ref},
        {"$set": {"merged_into": to_ref}},
    )

    # 4. Notify open widget on from_ref
    _publish_reconnected(from_ref, to_ref)


def identify(
    user_ref: str,
    phone: str | None = None,
    email: str | None = None,
    intent: str = "enquiry",
    bound_origin: str | None = None,
) -> dict:
    """Attach phone/email to a web session or reconnect to an existing web user.

    Never looks up WhatsApp users.
    """
    # FUTURE: OTP verification before payment. Client deferred this for low
    # friction. To enable, call send_otp() here when intent == "payment" and
    # return otp_required=True instead of proceeding. See verify_otp below.
    _ = intent  # payment and enquiry behave identically in V1

    user_ref = resolve_user(user_ref)
    updates: dict = {}

    normalised = None
    if phone:
        normalised = normalise_phone(phone)
        updates["identifiers.phone"] = normalised
    if email is not None:
        updates["identifiers.email"] = email

    if normalised:
        existing = idac.find_one(
            {
                "channel": "web",
                "identifiers.phone": normalised,
                "merged_into": None,
                "phone_number": {"$ne": user_ref},
            }
        )
        if existing:
            existing_ref = existing["phone_number"]
            link_sessions(user_ref, existing_ref)
            new_jwt = create_web_token(existing_ref, bound_origin=bound_origin)
            return {
                "status": "reconnected",
                "otp_required": False,
                "canonical_ref": existing_ref,
                "token": new_jwt,
            }

    if updates:
        idac.update_one({"phone_number": user_ref}, {"$set": updates}, upsert=True)

    return {
        "status": "identified",
        "otp_required": False,
        "canonical_ref": user_ref,
        "token": None,
    }


def send_otp(user_ref: str, phone: str) -> dict:
    """Store a 6-digit OTP (10 min TTL) and send via Gupshup template.

    NOT CALLED IN V1 — exists so enabling payment OTP is a one-line change.
    """
    normalised = normalise_phone(phone)
    code = f"{random.randint(0, 999999):06d}"
    expires_at = int(time.time()) + _OTP_TTL_SECONDS
    idac.update_one(
        {"phone_number": user_ref},
        {
            "$set": {
                "otp": {"code": code, "expires_at": expires_at, "attempts": 0},
                "identifiers.phone": normalised,
            }
        },
    )
    send_otp_template(phone_number=normalised, otp_code=code)
    return {"status": "otp_sent", "expires_at": expires_at}


def verify_otp(user_ref: str, code: str) -> dict:
    """Verify OTP on the user doc. NOT CALLED IN V1."""
    doc = idac.find_one({"phone_number": user_ref}, {"otp": 1})
    if not doc or not doc.get("otp"):
        return {"status": "invalid", "reason": "no_otp"}
    otp = doc["otp"]
    attempts = int(otp.get("attempts") or 0)
    if attempts >= _OTP_MAX_ATTEMPTS:
        return {"status": "invalid", "reason": "max_attempts"}
    if int(time.time()) > int(otp.get("expires_at") or 0):
        return {"status": "invalid", "reason": "expired"}

    if str(code).strip() != str(otp.get("code")):
        idac.update_one(
            {"phone_number": user_ref},
            {"$inc": {"otp.attempts": 1}},
        )
        return {"status": "invalid", "reason": "mismatch"}

    idac.update_one({"phone_number": user_ref}, {"$unset": {"otp": ""}})
    return {"status": "verified"}
