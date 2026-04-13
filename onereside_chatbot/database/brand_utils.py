import re

from pymongo import ReturnDocument

from onereside_chatbot.database.chroma.utils import add_brand, update_brand_embedding, delete_brand
from onereside_chatbot.database.collections import company
from onereside_chatbot.utils.logger_config import logger


def _generate_brand_id(brand_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", brand_name.lower()).strip("-")
    if not company.find_one({"brand_id": slug}, {"_id": 1}):
        return slug
    counter = 1
    while company.find_one({"brand_id": f"{slug}-{counter}"}, {"_id": 1}):
        counter += 1
    return f"{slug}-{counter}"


def get_brand_by_name(brand_name: str):
    """Get brand doc by name from QR message."""
    try:
        brand = company.find_one(
            {"brand_name": {"$regex": brand_name, "$options": "i"}},
            {"_id": 0},
        )
        if not brand:
            logger.exception("No brand found for given name.", extra={"brand_name": brand_name})
            return False
        return brand
    except Exception as e:
        logger.exception("Exception occurred while fetching brand.", extra={"brand_name": brand_name})
        raise e


def get_brand_by_id(brand_id: str):
    """Get brand doc by id."""
    try:
        brand = company.find_one({"brand_id": brand_id}, {"_id": 0})
        if not brand:
            logger.exception("No brand found for given id.", extra={"brand_id": brand_id})
            return False
        return brand
    except Exception as e:
        logger.exception("Exception occurred while fetching brand.", extra={"brand_id": brand_id})
        raise e


def get_brands_by_ids(brand_ids: list) -> list:
    """Get multiple brand docs by a list of brand_ids."""
    try:
        return list(company.find({"brand_id": {"$in": brand_ids}}, {"_id": 0}))
    except Exception as e:
        logger.exception("Exception occurred while fetching brands by ids.", extra={"brand_ids": brand_ids})
        raise e


def get_all_brands(skip: int = 0, limit: int = 20) -> tuple[int, list]:
    """Get paginated list of all brands. Returns (total, brands)."""
    try:
        total = company.count_documents({})
        projection = {"brand_id": 1, "brand_name": 1, "categories_offered": 1, "brand_description": 1}
        brands = list(company.find({}, projection).skip(skip).limit(limit))
        for b in brands:
            b["_id"] = str(b["_id"])
        logger.info("Fetched brands", extra={"skip": skip, "limit": limit, "total": total})
        return total, brands
    except Exception as e:
        logger.exception("Exception occurred while fetching all brands.")
        raise e


def get_brands_summary() -> list:
    """Get brand_id and brand_name for all brands (dropdown use)."""
    try:
        return list(company.find({}, {"_id": 0, "brand_id": 1, "brand_name": 1}))
    except Exception as e:
        logger.exception("Exception occurred while fetching brands summary.")
        raise e


def create_brand(data: dict) -> dict:
    """Insert a new brand into MongoDB with an auto-generated brand_id."""
    try:
        data["brand_id"] = _generate_brand_id(data["brand_name"])
        company.insert_one(data)
        data.pop("_id", None)
        add_brand(data)
        logger.info("Brand created successfully.", extra={"brand_id": data["brand_id"]})
        return data
    except Exception as e:
        logger.exception("Exception occurred while creating brand.")
        raise e


def update_brand(brand_id: str, update_data: dict) -> dict | None:
    """Update a brand by brand_id. brand_id itself cannot be changed."""
    try:
        result = company.find_one_and_update(
            {"brand_id": brand_id},
            {"$set": update_data},
            return_document=ReturnDocument.AFTER,
        )
        if not result:
            logger.warning("No brand found to update.", extra={"brand_id": brand_id})
            return None
        result.pop("_id", None)
        update_brand_embedding(result)
        logger.info("Brand updated successfully.", extra={"brand_id": brand_id})
        return result
    except Exception as e:
        logger.exception("Exception occurred while updating brand.", extra={"brand_id": brand_id})
        raise e


def remove_brand(brand_id: str) -> bool:
    """Delete a brand by brand_id. Returns True if found and deleted."""
    try:
        result = company.delete_one({"brand_id": brand_id})
        if result.deleted_count == 0:
            logger.warning("No brand found to delete.", extra={"brand_id": brand_id})
            return False
        delete_brand(brand_id)
        logger.info("Brand deleted successfully.", extra={"brand_id": brand_id})
        return True
    except Exception as e:
        logger.exception("Exception occurred while deleting brand.", extra={"brand_id": brand_id})
        raise e
