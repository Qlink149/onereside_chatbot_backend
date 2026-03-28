from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from onereside_chatbot.database.brand_utils import get_brand_by_id
from onereside_chatbot.database.product_utils import create_product, get_all_products, get_product_by_id, remove_product, update_product
from onereside_chatbot.routes.dependencies import verify_api_key

router = APIRouter(prefix="/products", tags=["products"])


class ProductCreate(BaseModel):
    brand_id: str
    name: str
    category: str
    type: str
    description: str
    style_tags: list[str]
    materials: list[str]
    colors_available: list[str]
    media_url: list[dict[str, Any]]
    price_inr: int
    delivery_weeks: int
    ideal_for: list[str]
    inventory_status: str


class ProductUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    type: str | None = None
    description: str | None = None
    style_tags: list[str] | None = None
    materials: list[str] | None = None
    colors_available: list[str] | None = None
    media_url: list[dict[str, Any]] | None = None
    price_inr: int | None = None
    delivery_weeks: int | None = None
    ideal_for: list[str] | None = None
    inventory_status: str | None = None


@router.post("", status_code=201)
def add_product(body: ProductCreate, _: str = Depends(verify_api_key)):
    """Create a new product. product_id is auto-generated. brand_id must exist."""
    if not get_brand_by_id(body.brand_id):
        raise HTTPException(status_code=404, detail=f"Brand '{body.brand_id}' not found")
    return create_product(body.model_dump())


@router.get("")
def list_products(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    brand_id: str | None = Query(None),
    category: str | None = Query(None),
    type: str | None = Query(None),
    _: str = Depends(verify_api_key),
):
    """List all products with optional filters and pagination."""
    skip = (page - 1) * limit
    total, products = get_all_products(skip=skip, limit=limit, brand_id=brand_id, category=category, type=type)
    return {"total": total, "page": page, "limit": limit, "data": products}


@router.get("/{product_id}")
def get_product(product_id: str, _: str = Depends(verify_api_key)):
    """Get a product by product_id."""
    product = get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.patch("/{product_id}")
def patch_product(product_id: str, body: ProductUpdate, _: str = Depends(verify_api_key)):
    """Update product details. product_id and brand_id cannot be changed."""
    update_data = body.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    updated = update_product(product_id, update_data)
    if not updated:
        raise HTTPException(status_code=404, detail="Product not found")
    return updated


@router.delete("/{product_id}", status_code=204)
def delete_product(product_id: str, _: str = Depends(verify_api_key)):
    """Delete a product from MongoDB and Chroma."""
    if not remove_product(product_id):
        raise HTTPException(status_code=404, detail="Product not found")
