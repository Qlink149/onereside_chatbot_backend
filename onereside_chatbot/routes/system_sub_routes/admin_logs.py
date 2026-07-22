from fastapi import APIRouter, Depends, Query

from onereside_chatbot.database.admin_log_utils import get_admin_logs
from onereside_chatbot.routes.dependencies import verify_api_key

router = APIRouter(prefix="/admin-logs", tags=["admin-logs"])


def _serialize(doc: dict) -> dict:
    doc["_id"] = str(doc["_id"])
    return doc


@router.get("")
def list_admin_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    action: str | None = Query(None),
    target_type: str | None = Query(None),
    _: str = Depends(verify_api_key),
):
    """List admin activity logs with optional filters and pagination."""
    skip = (page - 1) * limit
    total, logs = get_admin_logs(skip=skip, limit=limit, action=action, target_type=target_type)
    return {"total": total, "page": page, "limit": limit, "data": [_serialize(log) for log in logs]}
