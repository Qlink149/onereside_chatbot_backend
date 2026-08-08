import time

from bson import ObjectId
from pymongo import DESCENDING

from onereside_chatbot.database.collections import enquiries
from onereside_chatbot.utils.logger_config import logger

_LIST_PROJECTION = {
    "phone_number": 1,
    "contact_phone": 1,
    "username": 1,
    "type": 1,
    "product.product_id": 1,
    "product.name": 1,
    "product.brand_id": 1,
    "product.brand_name": 1,
    "product.category": 1,
    "brand.brand_id": 1,
    "brand.brand_name": 1,
    "status": 1,
    "created_at": 1,
}


def save_enquiry(enquiry_data: dict) -> str:
    """Save a new enquiry to the enquiries collection. Returns the inserted _id as string."""
    try:
        enquiry_data["status"] = "pending"
        enquiry_data["created_at"] = int(time.time())
        result = enquiries.insert_one(enquiry_data)
        logger.info(
            "Enquiry saved successfully",
            extra={"inserted_id": str(result.inserted_id)},
        )
        return str(result.inserted_id)
    except Exception as e:
        logger.exception("Failed to save enquiry.", extra={"exception": e})
        raise e


def get_all_enquiries(
    skip: int = 0,
    limit: int = 20,
    status: str | None = None,
    enquiry_type: str | None = None,
    brand_id: str | None = None,
    phone_number: str | None = None,
) -> tuple[int, list]:
    """Get paginated enquiries with optional filters. Returns (total, enquiries)."""
    try:
        query = {}
        if status:
            query["status"] = status
        if enquiry_type:
            query["type"] = enquiry_type
        if brand_id:
            query["$or"] = [
                {"product.brand_id": brand_id},
                {"brand.brand_id": brand_id},
            ]
        if phone_number:
            query["phone_number"] = phone_number

        total = enquiries.count_documents(query)
        docs = list(
            enquiries.find(query, _LIST_PROJECTION)
            .sort("created_at", DESCENDING)
            .skip(skip)
            .limit(limit)
        )
        for d in docs:
            d["_id"] = str(d["_id"])
        return total, docs
    except Exception as e:
        logger.exception("Exception occurred while fetching enquiries.")
        raise e


def get_enquiry_by_id(enquiry_id: ObjectId) -> dict | None:
    """Get full enquiry details by MongoDB ObjectId."""
    try:
        doc = enquiries.find_one({"_id": enquiry_id})
        if not doc:
            return None
        doc["_id"] = str(doc["_id"])
        return doc
    except Exception as e:
        logger.exception("Exception occurred while fetching enquiry.", extra={"enquiry_id": str(enquiry_id)})
        raise e


def update_enquiry_status(enquiry_id: ObjectId, status: str) -> dict | None:
    """Update the status of an enquiry."""
    try:
        result = enquiries.find_one_and_update(
            {"_id": enquiry_id},
            {"$set": {"status": status, "updated_at": int(time.time())}},
            return_document=True,
        )
        if result:
            result["_id"] = str(result["_id"])
        return result
    except Exception as e:
        logger.exception("Exception occurred while updating enquiry status.", extra={"enquiry_id": str(enquiry_id)})
        raise e
