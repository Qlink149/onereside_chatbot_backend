import time
from collections import defaultdict
from datetime import datetime

from bson import ObjectId
from pymongo import ReturnDocument

from onereside_chatbot.database.collections import (
    appoinments,
    git,
    idac,
    pims_calls,
    pims_systems,
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
    
def git_save_to_mongo(data):
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

        response = git.find_one_and_update(
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


def get_doc_by_id(doc_id: str):
    """Fetch a document by its _id and return a clean structured dict."""
    try:
        doc = idac.find_one({"_id": ObjectId(doc_id)})
        if not doc:
            logger.warning(
                "No document found for given ID", extra={"_id": doc_id}
            )
            return None

        new_doc = {
            "_id": str(doc["_id"]),
            "phone_number": doc.get("phone_number", ""),
            "username": doc.get("username", ""),
            "chat_history": doc.get("chat_history", []),
            "service_selected": doc.get("service_selected", ""),
            "updated_at": (
                doc["updated_at"].isoformat()
                if isinstance(doc.get("updated_at"), datetime)
                else doc.get("updated_at")
            ),
            "find_doctor": doc.get("Find a Doctor", 0),
            "direction": doc.get("Direction", 0),
            "contact_us": doc.get("Contact Us", 0),
            "book_an_appointment": doc.get("Book an Appointment", 0),
            "other": doc.get("Other", 0),
        }

        return new_doc

    except Exception as e:
        logger.exception(
            "Error fetching document by ID",
            extra={"exception": e, "_id": doc_id},
        )
        raise e


def get_all_docs():
    """Return all docs."""
    try:
        docs = list(
            idac.find(
                {},
                {
                    "_id": 1,
                    "phone_number": 1,
                    "updated_at": 1,
                    "username": 1,
                    "chat_history": 1,
                },
            ).sort("updated_at", -1)
        )
        for doc in docs:
            doc["_id"] = str(doc["_id"])
            doc["updated_at"] = (
                doc["updated_at"].isoformat()
                if isinstance(doc.get("updated_at"), datetime)
                else doc.get("updated_at")
            )
            doc["total_interaction"] = len(doc.get("chat_history", [])) // 2
            doc.pop("chat_history", None)
        return docs
    except Exception as e:
        logger.exception(
            "Error fetching all document summaries", extra={"exception": e}
        )
        raise e
    
# get all docs
def get_all_docs_dashboard(page: int = 1, limit: int = 20):
    """Return paginated docs with total pages."""
    try:
        skip = (page - 1) * limit

        total_docs = idac.count_documents({})
        total_pages = (total_docs + limit - 1) // limit

        docs = list(
            idac.find(
                {},
                {
                    "_id": 1,
                    "phone_number": 1,
                    "updated_at": 1,
                    "username": 1,
                    "chat_history": 1,
                },
            )
            .sort("updated_at", -1)
            .skip(skip)
            .limit(limit)
        )

        for doc in docs:
            doc["_id"] = str(doc["_id"])
            doc["updated_at"] = (
                doc["updated_at"].isoformat()
                if isinstance(doc.get("updated_at"), datetime)
                else doc.get("updated_at")
            )
            doc["total_interaction"] = len(doc.get("chat_history", [])) // 2
            doc.pop("chat_history", None)

        return {
            "page": page,
            "limit": limit,
            "total_docs": total_docs,
            "total_pages": total_pages,
            "docs": docs,
        }

    except Exception as e:
        logger.exception(
            "Error fetching all document summaries",
            extra={"exception": e}
        )
        raise e

# get recent docs  
def get_recent_docs(limit: int = 5):
    """Return the most recent docs."""
    try:
        docs = list(
            idac.find(
                {},
                {
                    "_id": 1,
                    "phone_number": 1,
                    "updated_at": 1,
                    "username": 1,
                    "chat_history": 1,
                },
            )
            .sort("updated_at", -1)
            .limit(limit)
        )

        for doc in docs:
            doc["_id"] = str(doc["_id"])
            doc["updated_at"] = (
                doc["updated_at"].isoformat()
                if isinstance(doc.get("updated_at"), datetime)
                else doc.get("updated_at")
            )
            doc["total_interaction"] = len(doc.get("chat_history", [])) // 2
            doc.pop("chat_history", None)

        return docs

    except Exception as e:
        logger.exception(
            "Error fetching recent docs", extra={"exception": e}
        )
        raise e


def get_full_analytics():
    """Generate complete analytics including interactions, unsubscribe, and site visit data."""
    try:
        docs = list(idac.find({}))
        if not docs:
            return {"success": False, "message": "No data found"}

        total_users = len(docs)
        total_interactions = 0
        service_counts = defaultdict(int)
        user_activity = []
        unsubscribed_users = []
        site_visit_users = []

        for doc in docs:
            chat_history = doc.get("chat_history", [])
            chat_len = (
                len(chat_history) // 2
            )  # user + assistant = 1 interaction
            total_interactions += chat_len

            username = doc.get("username", "")
            phone_number = doc.get("phone_number", "")
            user_activity.append(
                {
                    "username": username,
                    "phone_number": phone_number,
                    "interactions": chat_len,
                }
            )

            service_counts["find_doctor"] += doc.get("Find a Doctor", 0)
            service_counts["direction"] += doc.get("Direction", 0)
            service_counts["other"] += doc.get("Other", 0)
            service_counts["contact_us"] += doc.get("Contact Us", 0)
            service_counts["book_an_appointment"] += doc.get(
                "Book an Appointment", 0
            )

            for msg in chat_history:
                if msg.get("role") == "user" and isinstance(
                    msg.get("content"), str
                ):
                    # detect unsubscribe
                    if "stop" in msg["content"].lower():
                        unsubscribed_users.append(
                            {"username": username, "phone_number": phone_number}
                        )
                        break

                if msg.get("role") == "assistant" and isinstance(
                    msg.get("content"), str
                ):
                    # detect site visit confirmation message
                    if (
                        "thanks! our team will confirm your appointment soon."
                        in msg["content"].lower()
                    ):  # noqa
                        site_visit_users.append(
                            {"username": username, "phone_number": phone_number}
                        )
                        break

        avg_interactions_per_user = (
            round(total_interactions / total_users, 2) if total_users else 0
        )

        most_active_user = (
            max(user_activity, key=lambda x: x["interactions"])
            if user_activity
            else None
        )

        analytics = {
            "success": True,
            "summary": {
                "total_users": total_users,
                "total_interactions": total_interactions,
                "avg_interactions_per_user": avg_interactions_per_user,
                "most_active_user": most_active_user,
                "service_wise_interactions": dict(service_counts),
                "total_unsubscribed_users": len(unsubscribed_users),
                "unsubscribed_users": unsubscribed_users,
                "total_appointment_users": len(site_visit_users),
                "appointment_booked_users": site_visit_users,
            },
        }

        return analytics

    except Exception as e:
        logger.exception(
            "Error generating full analytics", extra={"exception": e}
        )
        raise e


def add_registration(data):
    """Function to add registration."""
    try:
        data["created_at"] = datetime.utcnow()

        appoinments.insert_one(data)

    except Exception as e:
        logger.error(
            "Error occured while returning the analytics",
            extra={
                "error": str(e)
            }
        )

        return None
    
def add_call_entry(data: dict):
    """Create or update call entry based on callSid."""
    try:
        pims_calls.update_one(
            {"callSid": data.get("callSid")},
            {
                "$set": {
                    **data,
                    "updated_at": int(time.time())
                },
                "$setOnInsert": {
                    "created_at": int(time.time())
                }
            },
            upsert=True
        )
    except Exception as e:
        logger.exception("Error adding/updating call entry", extra={"error": str(e)})
        raise



def list_calls(page: int = 1, limit: int = 20):
    """Return paginated call logs."""
    try:
        skip = (page - 1) * limit

        total_docs = pims_calls.count_documents({})
        total_pages = (total_docs + limit - 1) // limit

        docs = list(
            pims_calls.find(
                {},
                {
                    "_id": 1,
                    "status": 1,
                    "created_at": 1,
                    "telephonyData.recordingUrl": 1,
                    "contextDetails.recipientPhoneNumber": 1,
                },
            )
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )

        # clean + flatten
        cleaned = []
        for d in docs:
            cleaned.append({
                "_id": str(d["_id"]),
                "recipientPhoneNumber": d.get("contextDetails", {}).get("recipientPhoneNumber"),
                "recordingUrl": d.get("telephonyData", {}).get("recordingUrl"),
                "status": d.get("status"),
                "created_at": d.get("created_at"),
            })

        return {
            "page": page,
            "limit": limit,
            "total_docs": total_docs,
            "total_pages": total_pages,
            "calls": cleaned,
        }

    except Exception as e:
        logger.exception("Error listing calls", extra={"error": e})
        raise e

def get_recent_calls(limit: int = 5):
    """Return the most recent call logs."""
    try:
        docs = list(
            pims_calls.find(
                {},
                {
                    "_id": 1,
                    "status": 1,
                    "created_at": 1,
                    "telephonyData.recordingUrl": 1,
                    "contextDetails.recipientPhoneNumber": 1,
                },
            )
            .sort("created_at", -1)
            .limit(limit)
        )

        cleaned = []
        for d in docs:
            cleaned.append({
                "_id": str(d["_id"]),
                "recipientPhoneNumber": d.get("contextDetails", {}).get("recipientPhoneNumber"),
                "recordingUrl": d.get("telephonyData", {}).get("recordingUrl"),
                "status": d.get("status"),
                "created_at": d.get("created_at"),
            })

        return cleaned

    except Exception as e:
        logger.exception("Error fetching recent calls", extra={"error": e})
        raise e
    
def get_call_by_id(call_id: str):
    """Return full call document by ID."""
    try:
        doc = pims_calls.find_one({"_id": ObjectId(call_id)})

        if not doc:
            return None

        # convert _id to string
        doc["_id"] = str(doc["_id"])

        return doc

    except Exception as e:
        logger.exception("Error fetching call by ID", extra={"error": e})
        raise e
    
def return_system_prompt():
    try:
        doc = pims_systems.find_one(
            {"category": "system_prompt"},
            {"_id": 0, "prompt": 1}
        )
        return doc.get("prompt") if doc else ""
    except Exception as e:
        raise e


def return_kb_prompt():
    try:
        doc = pims_systems.find_one(
            {"category": "kb_prompt"},
            {"_id": 0, "kb": 1}
        )
        return doc.get("kb") if doc else {}
    except Exception as e:
        raise e


def update_system_prompt(prompt: str):
    try:
        result = pims_systems.update_one(
            {"category": "system_prompt"},
            {"$set": {"prompt": prompt}},
            upsert=False
        )
        return result.modified_count > 0
    except Exception as e:
        raise e


def update_kb_prompt(kb: dict):
    try:
        result = pims_systems.update_one(
            {"category": "kb_prompt"},   # ✅ FIXED
            {"$set": {"kb": kb}},
            upsert=False
        )
        return result.modified_count > 0
    except Exception as e:
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