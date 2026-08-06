from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query

from onereside_chatbot.database.admin_log_utils import log_admin_action
from onereside_chatbot.database.user_utils import (
    delete_user_profile,
    get_all_users,
    get_user_by_object_id,
    get_user_profile,
)
from onereside_chatbot.routes.dependencies import verify_api_key

router = APIRouter(prefix="/users", tags=["users"])


def _serialize(doc: dict) -> dict:
    doc["_id"] = str(doc["_id"])
    return doc


@router.get("")
def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    channel: str | None = Query(None, pattern="^(whatsapp|web)$"),
    _: str = Depends(verify_api_key),
):
    """List all users with pagination. Optional channel=whatsapp|web filter."""
    skip = (page - 1) * limit
    total, users = get_all_users(skip=skip, limit=limit, channel=channel)
    return {"total": total, "page": page, "limit": limit, "data": [_serialize(u) for u in users]}


@router.get("/phone/{phone_number}")
def get_user_by_phone(phone_number: str, _: str = Depends(verify_api_key)):
    """Get a user by phone number."""
    user = get_user_profile(phone_number)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _serialize(user)


@router.get("/{user_id}")
def get_user_by_id(user_id: str, _: str = Depends(verify_api_key)):
    """Get a user by MongoDB ObjectId."""
    try:
        oid = ObjectId(user_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    user = get_user_by_object_id(oid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _serialize(user)


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: str, _: str = Depends(verify_api_key)):
    """Delete a user and their whole conversation history.

    Orders, enquiries and payments are business records and are left intact.
    """
    try:
        oid = ObjectId(user_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid user ID format")

    deleted = delete_user_profile(oid)
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")

    counts = deleted.get("_deleted_counts", {})
    log_admin_action(
        action="delete_user",
        target_type="user",
        target_id=user_id,
        details={
            "phone_number": deleted.get("phone_number"),
            "username": deleted.get("username"),
            "messages_deleted": counts.get("messages", 0),
        },
    )
