from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query

from onereside_chatbot.database.payment_utils import (
    get_all_payments,
    get_payment_by_id,
    get_payments_by_phone,
)
from onereside_chatbot.routes.dependencies import verify_api_key

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("")
def list_payments(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _: str = Depends(verify_api_key),
):
    """List all payments with pagination."""
    skip = (page - 1) * limit
    total, docs = get_all_payments(skip=skip, limit=limit)
    return {"total": total, "page": page, "limit": limit, "data": docs}


@router.get("/phone/{phone_number}")
def list_payments_by_phone(
    phone_number: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _: str = Depends(verify_api_key),
):
    """Get all payments by phone number (pass without leading +)."""
    skip = (page - 1) * limit
    total, docs = get_payments_by_phone(phone_number, skip=skip, limit=limit)
    return {"total": total, "page": page, "limit": limit, "data": docs}


@router.get("/{payment_id}")
def get_payment(payment_id: str, _: str = Depends(verify_api_key)):
    """Get full payment details by MongoDB ObjectId."""
    try:
        oid = ObjectId(payment_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid payment ID format")
    payment = get_payment_by_id(oid)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return payment
