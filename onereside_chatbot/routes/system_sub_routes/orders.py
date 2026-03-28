from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query

from onereside_chatbot.database.order_utils import (
    get_all_orders,
    get_order_by_id,
    get_orders_by_brand,
    get_orders_by_phone,
    get_orders_by_product,
)
from onereside_chatbot.routes.dependencies import verify_api_key

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("")
def list_orders(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    payment_status: str | None = Query(None),
    brand_id: str | None = Query(None),
    product_id: str | None = Query(None),
    _: str = Depends(verify_api_key),
):
    """List all orders with optional filters and pagination."""
    skip = (page - 1) * limit
    total, docs = get_all_orders(skip=skip, limit=limit, payment_status=payment_status, brand_id=brand_id, product_id=product_id)
    return {"total": total, "page": page, "limit": limit, "data": docs}


@router.get("/phone/{phone_number}")
def list_orders_by_phone(
    phone_number: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _: str = Depends(verify_api_key),
):
    """Get all orders for a phone number."""
    skip = (page - 1) * limit
    total, docs = get_orders_by_phone(phone_number, skip=skip, limit=limit)
    return {"total": total, "page": page, "limit": limit, "data": docs}


@router.get("/product/{product_id}")
def list_orders_by_product(
    product_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _: str = Depends(verify_api_key),
):
    """Get all orders for a product_id."""
    skip = (page - 1) * limit
    total, docs = get_orders_by_product(product_id, skip=skip, limit=limit)
    return {"total": total, "page": page, "limit": limit, "data": docs}


@router.get("/brand/{brand_id}")
def list_orders_by_brand(
    brand_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _: str = Depends(verify_api_key),
):
    """Get all orders for a brand_id."""
    skip = (page - 1) * limit
    total, docs = get_orders_by_brand(brand_id, skip=skip, limit=limit)
    return {"total": total, "page": page, "limit": limit, "data": docs}


@router.get("/{order_id}")
def get_order(order_id: str, _: str = Depends(verify_api_key)):
    """Get full order details by MongoDB ObjectId."""
    try:
        oid = ObjectId(order_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid order ID format")
    order = get_order_by_id(oid)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order
