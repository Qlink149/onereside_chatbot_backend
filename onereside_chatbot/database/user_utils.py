import time

from bson import ObjectId
from pymongo import ReturnDocument

from onereside_chatbot.constants import CHAT_HISTORY_MAX
from onereside_chatbot.database.collections import idac
from onereside_chatbot.database.message_utils import delete_messages_by_phone, save_turn_messages
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
            user=query, assistant=assistant, phone_number=phone_number,
            received_at=data.get("received_at"),
        )

        # $push (not $set) the new entries so a concurrent write (e.g. a human
        # takeover message landing mid-pipeline) can't be clobbered; $slice keeps
        # the embedded array a rolling window — full history lives in `messages`.
        profile_set = {k: v for k, v in user_profile_data.items() if k != "chat_history"}
        profile_set["updated_at"] = int(time.time())
        profile_set["username"] = data["whatsapp_username"]

        response = idac.find_one_and_update(
            {"phone_number": phone_number},
            {
                "$set": profile_set,
                "$push": {"chat_history": {"$each": new_chat, "$slice": -CHAT_HISTORY_MAX}},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

        # Per-message store with debug context for the admin dashboard
        save_turn_messages(data)

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


def get_all_users(skip: int = 0, limit: int = 20, channel: str | None = None) -> tuple[int, list]:
    """Get paginated list of all users. Returns (total, users).

    channel=web      -> only web widget sessions
    channel=whatsapp or omitted -> exclude web (existing WhatsApp docs have no channel field)
    """
    try:
        if channel == "web":
            query = {"channel": "web"}
        else:
            # $ne so legacy WhatsApp docs without a channel field are included
            query = {"channel": {"$ne": "web"}}
        total = idac.count_documents(query)
        projection = {
            "phone_number": 1,
            "username": 1,
            "updated_at": 1,
            "agent_request": 1,
            "identifiers": 1,
            "channel": 1,
        }
        users = list(idac.find(query, projection).sort("updated_at", -1).skip(skip).limit(limit))
        for user in users:
            phone = user.get("phone_number") or ""
            is_web = phone.startswith("web:") or user.get("channel") == "web"
            user["channel"] = "web" if is_web else "whatsapp"
            identified = (user.get("identifiers") or {}).get("phone")
            user["identified_phone"] = identified if identified else None
            also_on_whatsapp = False
            if identified:
                also_on_whatsapp = bool(
                    idac.find_one(
                        {"phone_number": identified, "channel": {"$exists": False}},
                        {"_id": 1},
                    )
                )
            user["also_on_whatsapp"] = also_on_whatsapp
        logger.info("Fetched users", extra={"skip": skip, "limit": limit, "total": total, "channel": channel})
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

def delete_user_profile(user_id: ObjectId) -> dict | None:
    """Delete a user and their whole conversation history.

    Removes the profile doc (including the embedded ``chat_history``) and every
    per-message doc in ``messages``. Orders, enquiries and payments are business
    records and are deliberately kept.

    Messages are removed before the profile itself, so a mid-way failure leaves
    the user visible in the dashboard and the delete can be retried.

    Returns the deleted profile doc, or None if not found.
    """
    try:
        user = idac.find_one({"_id": user_id})
        if not user:
            logger.warning("No user found to delete.", extra={"user_id": str(user_id)})
            return None

        phone_number = user.get("phone_number")
        message_count = 0
        if phone_number:
            message_count = delete_messages_by_phone(phone_number)
        else:
            logger.warning(
                "User has no phone number; skipping message cleanup.",
                extra={"user_id": str(user_id)},
            )

        idac.delete_one({"_id": user_id})
        logger.info(
            "User deleted successfully.",
            extra={
                "user_id": str(user_id),
                "phone_number": phone_number,
                "messages_deleted": message_count,
            },
        )
        user["_deleted_counts"] = {"messages": message_count}
        return user
    except Exception:
        logger.exception("Exception occurred while deleting user profile.", extra={"user_id": str(user_id)})
        raise


def update_agent_request_flag(user_id: ObjectId):
    """Function to update the request agent flag."""
    try:
        result = idac.update_one(
            {"_id": user_id},
            {
                "$set": {
                    "agent_request": False
                }
            }
        )

        if result.matched_count == 0:
            logger.warning("No document found to update", extra={"user_id": str(user_id)})

        return result.modified_count > 0

    except Exception:
        logger.exception(
            "Exception occurred while updating agent request flag.",
            extra={"user_id": str(user_id)}
        )
        raise


def set_agent_request(phone_number: str, active: bool) -> None:
    """Set agent_request on the user profile immediately (e.g. before slow side effects)."""
    idac.update_one(
        {"phone_number": phone_number},
        {"$set": {"agent_request": active, "updated_at": int(time.time())}},
    )
