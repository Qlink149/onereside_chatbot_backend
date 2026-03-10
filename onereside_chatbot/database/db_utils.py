import time
from collections import defaultdict
from datetime import datetime

from bson import ObjectId
from pymongo import ReturnDocument

from onereside_chatbot.database.collections import (
    idac,
    company,
    product
)
from onereside_chatbot.utils.format_chathistory import format_chat_history
from onereside_chatbot.utils.logger_config import logger


def mongo_search(query, collection):
    """Executes a MongoDB search based on a given query."""
    try:
        logger.debug("Executing MongoDB search", extra={"query": query})
        results = list(collection.find(query))
        logger.info("Found results of length", extra={"length": len(results)})
        return results

    except Exception as e:
        logger.exception("MongoDB search failed:", extra={"exception": e})
        raise e


def save_to_mongo(data):
    """Saves the data to a MongoDB collection."""
    try:
        logger.info(
            "Request received to save user profile with data",
            extra={"phone_number": data["phone_number"]},
        )
        query = data["messages"]
        
        assistant = data["bot_response"] if "bot_response" in data else None
        phone_number = data["phone_number"]
        user_profile_data = data["user_profile"]

        new_chat = format_chat_history(
            user=query, assistant=assistant, phone_number=phone_number
        )

        current_history = user_profile_data.get("chat_history", [])
        user_profile_data["chat_history"] = current_history + new_chat
        user_profile_data["updated_at"] = datetime.now()
        user_profile_data["username"] = data["whatsapp_username"]

        response = idac.find_one_and_update(
            {"phone_number": phone_number},
            {"$set": user_profile_data},
            upsert=True,  # Insert if document doesn't exist
            return_document=ReturnDocument.AFTER,
        )

        logger.info(
            "User profile saved successfully",
            extra={
                "response_id": response.get("_id"),
                "phone_number": phone_number,
            },
        )
        response.pop("_id")
        return response
    except Exception as e:
        logger.exception(
            "MongoDB save failed:",
            extra={"exception": e, "phone_number": phone_number},
        )
        raise e



def save_user_profile(phone_number: str, profile_data: dict):
    """Saves data to user profile collection."""
    try:
        logger.info(
            "Request received to save user profile with data",
            extra={"profile_data": profile_data, "phone_number": phone_number},
        )
        profile_data["created_at"] = datetime.now()
        profile_data["updated_at"] = datetime.now()

        response = idac.find_one_and_update(
            {"phone_number": phone_number},
            {"$set": profile_data},
            upsert=True,  # Insert if document doesn't exist
            return_document=True,
        )

        logger.info(
            "User profile saved successfully",
            extra={
                "response_id": response.get("_id"),
                "phone_number": phone_number,
            },
        )
        response.pop("_id")
        return response
    except Exception as e:
        logger.exception(
            "MongoDB save failed:",
            extra={"exception": e, "phone_number": phone_number},
        )
        raise e


def get_user_profile(phone_number: str):
    """Get User Profile data."""
    try:
        profile = idac.find_one({"phone_number": phone_number})

        if not profile:
            logger.exception(
                "No profile exists for phone number.",
                extra={"phone_number": phone_number},
            )
            return None

        return profile
    except Exception as e:
        logger.exception(
            "Exception occured while fetching user profile.",
            extra={"phone_number": phone_number},
        )
        raise e


# one reside

def get_brand_by_name(brand_name: str):
    """Get brand doc by name from QR message."""
    try:
        brand = company.find_one(
            {"brand_name": {"$regex": brand_name, "$options": "i"}},
            {"_id": 0}
        )

        if not brand:
            logger.exception(
                "No brand found for given name.",
                extra={"brand_name": brand_name},
            )
            return False

        return brand

    except Exception as e:
        logger.exception(
            "Exception occurred while fetching brand.",
            extra={"brand_name": brand_name},
        )
        raise e
    

def get_brand_by_id(brand_id: str):
    """Get brand doc by id."""
    try:
        brand = company.find_one(
            {"brand_id": brand_id},
            {"_id": 0}
        )

        if not brand:
            logger.exception(
                "No brand found for given id.",
                extra={"brand_id": brand_id},
            )
            return False

        return brand

    except Exception as e:
        logger.exception(
            "Exception occurred while fetching brand.",
            extra={"brand_id": brand_id},
        )
        raise e
    

def get_brands_by_ids(brand_ids: list) -> list:
    """Get multiple brand docs by a list of brand_ids."""
    try:
        return list(company.find({"brand_id": {"$in": brand_ids}}, {"_id": 0}))
    except Exception as e:
        logger.exception(
            "Exception occurred while fetching brands by ids.",
            extra={"brand_ids": brand_ids},
        )
        raise e


def get_product_by_id(product_id: str):
    """Get product doc by id."""
    try:
        product_doc = product.find_one(
            {"product_id": product_id},
            {"_id": 0}
        )

        if not product_doc:
            logger.exception(
                "No product found for given id.",
                extra={"product_id": product_id},
            )
            return False

        return product_doc

    except Exception as e:
        logger.exception(
            "Exception occurred while fetching product_id.",
            extra={"product_id": product_id},
        )
        raise e