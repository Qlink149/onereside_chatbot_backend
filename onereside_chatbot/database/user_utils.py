import time

from bson import ObjectId
from pymongo import ReturnDocument

from onereside_chatbot.database.collections import idac
from onereside_chatbot.utils.format_chathistory import format_chat_history
from onereside_chatbot.utils.logger_config import logger


def save_to_mongo(data):
    """Saves the data to a MongoDB collection."""
    phone_number = data["phone_number"]
    try:
        logger.info(
            "Request received to save user profile with data",
            extra={"phone_number": phone_number},
        )
        query = data["messages"]
        assistant = data["bot_response"] if "bot_response" in data else None
        user_profile_data = data["user_profile"]

        new_chat = format_chat_history(
            user=query, assistant=assistant, phone_number=phone_number
        )

        current_history = user_profile_data.get("chat_history", [])
        user_profile_data["chat_history"] = current_history + new_chat
        user_profile_data["updated_at"] = int(time.time())
        user_profile_data["username"] = data["whatsapp_username"]

        response = idac.find_one_and_update(
            {"phone_number": phone_number},
            {"$set": user_profile_data},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

        logger.info(
            "User profile saved successfully",
            extra={"response_id": response.get("_id"), "phone_number": phone_number},
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
        profile_data["created_at"] = int(time.time())
        profile_data["updated_at"] = int(time.time())

        response = idac.find_one_and_update(
            {"phone_number": phone_number},
            {"$set": profile_data},
            upsert=True,
            return_document=True,
        )

        logger.info(
            "User profile saved successfully",
            extra={"response_id": response.get("_id"), "phone_number": phone_number},
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


def get_all_users(skip: int = 0, limit: int = 20) -> tuple[int, list]:
    """Get paginated list of all users. Returns (total, users)."""
    try:
        total = idac.count_documents({})
        projection = {"phone_number": 1, "username": 1, "updated_at": 1}
        users = list(idac.find({}, projection).sort("updated_at", -1).skip(skip).limit(limit))
        logger.info("Fetched users", extra={"skip": skip, "limit": limit, "total": total})
        return total, users
    except Exception as e:
        logger.exception("Exception occurred while fetching all users.")
        raise e


def get_user_by_object_id(user_id: ObjectId):
    """Get a user by MongoDB ObjectId."""
    try:
        user = idac.find_one({"_id": user_id})
        if not user:
            logger.exception("No user found for given id.", extra={"user_id": str(user_id)})
            return None
        return user
    except Exception as e:
        logger.exception("Exception occurred while fetching user by id.", extra={"user_id": str(user_id)})
        raise e
