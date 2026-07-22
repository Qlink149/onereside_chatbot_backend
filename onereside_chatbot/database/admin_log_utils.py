import time

from onereside_chatbot.database.collections import admin_logs
from onereside_chatbot.utils.logger_config import logger


def log_admin_action(action: str, target_type: str, target_id: str, performed_by: str = "admin", details: dict | None = None) -> dict:
    """Record an admin activity entry (e.g. deleting a user)."""
    try:
        entry = {
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "performed_by": performed_by,
            "details": details or {},
            "timestamp": int(time.time()),
        }
        result = admin_logs.insert_one(entry)
        entry["_id"] = result.inserted_id
        logger.info("Admin action logged.", extra={"action": action, "target_type": target_type, "target_id": target_id})
        return entry
    except Exception:
        logger.exception("Exception occurred while logging admin action.", extra={"action": action, "target_type": target_type, "target_id": target_id})
        raise


def get_admin_logs(skip: int = 0, limit: int = 20, action: str | None = None, target_type: str | None = None) -> tuple[int, list]:
    """Get paginated admin log entries, optionally filtered by action or target_type."""
    try:
        query: dict = {}
        if action:
            query["action"] = action
        if target_type:
            query["target_type"] = target_type

        total = admin_logs.count_documents(query)
        logs = list(admin_logs.find(query).sort("timestamp", -1).skip(skip).limit(limit))
        logger.info("Fetched admin logs", extra={"skip": skip, "limit": limit, "total": total})
        return total, logs
    except Exception:
        logger.exception("Exception occurred while fetching admin logs.")
        raise
