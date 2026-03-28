import time

from bson import ObjectId
from pymongo import DESCENDING

from onereside_chatbot.database.collections import payments
from onereside_chatbot.utils.logger_config import logger

_LIST_PROJECTION = {
    "payment_id": 1,
    "payment_link_id": 1,
    "event": 1,
    "amount": 1,
    "currency": 1,
    "status": 1,
    "method": 1,
    "contact": 1,
    "captured": 1,
    "created_at": 1,
    "raw_payload": 0,
}


def save_payment(payment_data: dict) -> dict:
    """Save Razorpay payment details to the payments collection."""
    try:
        payment_data["created_at"] = int(time.time())
        result = payments.insert_one(payment_data)
        logger.info(
            "Payment saved successfully",
            extra={
                "payment_id": payment_data.get("payment_id"),
                "inserted_id": str(result.inserted_id),
            },
        )
        return {"inserted_id": str(result.inserted_id)}
    except Exception as e:
        logger.exception("Failed to save payment.", extra={"exception": e})
        raise e


def get_all_payments(skip: int = 0, limit: int = 20) -> tuple[int, list]:
    """Get paginated list of all payments. Returns (total, payments)."""
    try:
        total = payments.count_documents({})
        docs = list(payments.find({}, _LIST_PROJECTION).sort("created_at", DESCENDING).skip(skip).limit(limit))
        for d in docs:
            d["_id"] = str(d["_id"])
        logger.info("Fetched payments", extra={"total": total})
        return total, docs
    except Exception as e:
        logger.exception("Exception occurred while fetching payments.")
        raise e


def get_payments_by_phone(phone_number: str, skip: int = 0, limit: int = 20) -> tuple[int, list]:
    """Get paginated payments by phone number (with or without leading +). Returns (total, payments)."""
    try:
        normalized = phone_number.lstrip("+")
        query = {"contact": {"$regex": f"\\+?{normalized}$"}}
        total = payments.count_documents(query)
        docs = list(payments.find(query, _LIST_PROJECTION).sort("created_at", DESCENDING).skip(skip).limit(limit))
        for d in docs:
            d["_id"] = str(d["_id"])
        return total, docs
    except Exception as e:
        logger.exception("Exception occurred while fetching payments by phone.", extra={"phone_number": phone_number})
        raise e


def get_payment_by_id(payment_oid: ObjectId) -> dict | None:
    """Get full payment details by MongoDB ObjectId."""
    try:
        doc = payments.find_one({"_id": payment_oid})
        if not doc:
            return None
        doc["_id"] = str(doc["_id"])
        return doc
    except Exception as e:
        logger.exception("Exception occurred while fetching payment.", extra={"payment_oid": str(payment_oid)})
        raise e
