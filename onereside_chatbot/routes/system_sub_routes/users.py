from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query

from onereside_chatbot.database.user_utils import (
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
    _: str = Depends(verify_api_key),
):
    """List all users with pagination."""
    skip = (page - 1) * limit
    total, users = get_all_users(skip=skip, limit=limit)
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
