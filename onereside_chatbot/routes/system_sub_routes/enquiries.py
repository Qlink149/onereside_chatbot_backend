from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from onereside_chatbot.database.enquiry_utils import (
    get_all_enquiries,
    get_enquiry_by_id,
    update_enquiry_status,
)
from onereside_chatbot.routes.dependencies import verify_api_key

router = APIRouter(prefix="/enquiries", tags=["enquiries"])


class EnquiryStatusUpdate(BaseModel):
    status: str


@router.get("")
def list_enquiries(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    type: str | None = Query(None, description="Filter by enquiry type: brand_enquiry or product_enquiry"),
    brand_id: str | None = Query(None),
    phone_number: str | None = Query(None),
    _: str = Depends(verify_api_key),
):
    """List all enquiries with optional filters and pagination."""
    skip = (page - 1) * limit
    total, docs = get_all_enquiries(
        skip=skip,
        limit=limit,
        status=status,
        enquiry_type=type,
        brand_id=brand_id,
        phone_number=phone_number,
    )
    return {"total": total, "page": page, "limit": limit, "data": docs}


@router.get("/{enquiry_id}")
def get_enquiry(enquiry_id: str, _: str = Depends(verify_api_key)):
    """Get full enquiry details by MongoDB ObjectId."""
    try:
        oid = ObjectId(enquiry_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid enquiry ID format")
    enquiry = get_enquiry_by_id(oid)
    if not enquiry:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    return enquiry


@router.patch("/{enquiry_id}/status")
def patch_enquiry_status(
    enquiry_id: str,
    body: EnquiryStatusUpdate,
    _: str = Depends(verify_api_key),
):
    """Update the status of an enquiry (e.g. pending → contacted → closed)."""
    try:
        oid = ObjectId(enquiry_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid enquiry ID format")
    updated = update_enquiry_status(oid, body.status)
    if not updated:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    return updated
