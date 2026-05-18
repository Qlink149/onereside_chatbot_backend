import io
import re
import uuid
from typing import Any, Literal

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel

from onereside_chatbot.database.brand_utils import get_brand_by_id
from onereside_chatbot.database.product_utils import create_product, get_all_products, get_product_by_id, remove_product, update_product
from onereside_chatbot.database.storage.r2_utils import upload_media
from onereside_chatbot.routes.dependencies import verify_api_key

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "video/mp4"}
LISTING_TYPES = Literal["product", "custom_product", "service"]

router = APIRouter(prefix="/products", tags=["products"])


class ProductCreate(BaseModel):
    brand_id: str
    name: str
    category: str
    listing_type: LISTING_TYPES = "product"
    description: str
    style_tags: list[str] | None = None
    materials: list[str] | None = None
    colors_available: list[str] | None = None
    size: str | None = None
    media_url: list[dict[str, Any]] = []
    price_inr: int | None = None
    delivery_weeks: int
    ideal_for: list[str] | None = None
    deliverables: list[str] | None = None
    inventory_status: str


class ProductUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    listing_type: LISTING_TYPES | None = None
    description: str | None = None
    style_tags: list[str] | None = None
    materials: list[str] | None = None
    colors_available: list[str] | None = None
    size: str | None = None
    media_url: list[dict[str, Any]] | None = None
    price_inr: int | None = None
    delivery_weeks: int | None = None
    ideal_for: list[str] | None = None
    deliverables: list[str] | None = None
    inventory_status: str | None = None


@router.post("", status_code=201)
def add_product(body: ProductCreate, _: str = Depends(verify_api_key)):
    """Create a new product. product_id is auto-generated. brand_id must exist."""
    if not get_brand_by_id(body.brand_id):
        raise HTTPException(status_code=404, detail=f"Brand '{body.brand_id}' not found")
    data = body.model_dump()
    if data.get("price_inr") == 0:
        data["price_inr"] = None
    return create_product(data)


@router.get("")
def list_products(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    brand_id: str | None = Query(None),
    category: str | None = Query(None),
    listing_type: str | None = Query(None),
    _: str = Depends(verify_api_key),
):
    """List all products with optional filters and pagination."""
    skip = (page - 1) * limit
    total, products = get_all_products(skip=skip, limit=limit, brand_id=brand_id, category=category, listing_type=listing_type)
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


@router.post("/media/upload", status_code=201)
async def upload_product_media(
    files: list[UploadFile] = File(...),
    _: str = Depends(verify_api_key),
):
    """Upload one or more media files to R2. Returns media objects ready to use in product create/update."""
    results = []
    for file in files:
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}")
        ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "jpg"
        key = f"products/{uuid.uuid4().hex}.{ext}"
        media_type = "video" if file.content_type.startswith("video") else "image"
        url = upload_media(file.file, key, file.content_type)
        results.append({"type": media_type, "url": url})
    return {"media": results}


@router.post("/bulk-upload", status_code=201)
async def bulk_upload_products(
    brand_id: str = Query(...),
    listing_type: LISTING_TYPES | None = Query(None),
    file: UploadFile = File(...),
    _: str = Depends(verify_api_key),
):
    """Bulk create products from a CSV or Excel sheet. product_id is auto-generated; sheet's product_id and media_url columns are ignored."""
    if not get_brand_by_id(brand_id):
        raise HTTPException(status_code=404, detail=f"Brand '{brand_id}' not found")

    content = await file.read()
    filename = file.filename or ""

    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        elif filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(content))
        else:
            raise HTTPException(status_code=400, detail="Only .csv, .xlsx, and .xls files are supported")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Could not parse the file. Ensure it is a valid CSV or Excel file.")

    def split_csv_field(value) -> list[str]:
        if pd.isna(value) or str(value).strip() in ("", "-"):
            return []
        return [item.strip() for item in re.split(r",|،", str(value)) if item.strip()]

    def parse_int(value) -> int | None:
        if pd.isna(value) or str(value).strip() in ("", "-"):
            return None
        match = re.search(r"\d+", str(value))
        return int(match.group()) if match else None

    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

    results = {"created": [], "failed": []}

    for idx, row in df.iterrows():
        row_num = int(idx) + 2  # 1-based + header row
        try:
            if listing_type:
                raw_listing_type = listing_type
            else:
                raw_listing_type = str(row.get("listing_type", "product")).strip().lower()
                if raw_listing_type not in ("product", "custom_product", "service"):
                    raw_listing_type = "product"

            data = {
                "brand_id": brand_id,
                "name": str(row.get("name", "")).strip(),
                "category": str(row.get("category", "")).strip(),
                "listing_type": raw_listing_type,
                "description": str(row.get("description", "")).strip(),
                "size": str(row.get("size", "")).strip() or None,
                "style_tags": split_csv_field(row.get("style_tags")),
                "materials": split_csv_field(row.get("materials")),
                "colors_available": split_csv_field(row.get("colors_available")),
                "ideal_for": split_csv_field(row.get("ideal_for")),
                "deliverables": split_csv_field(row.get("deliverables")),
                "price_inr": parse_int(row.get("price_inr")),
                "delivery_weeks": parse_int(row.get("delivery_weeks")) or 0,
                "inventory_status": str(row.get("inventory_status", "in_stock")).strip(),
                "media_url": [],
            }

            if not data["name"] or not data["category"]:
                raise ValueError("name and category are required")

            product = create_product(data)
            results["created"].append({"row": row_num, "product_id": product["product_id"], "name": product["name"]})

        except Exception as e:
            results["failed"].append({"row": row_num, "reason": str(e)})

    return results


@router.delete("/{product_id}", status_code=204)
def delete_product(product_id: str, _: str = Depends(verify_api_key)):
    """Delete a product from MongoDB and Chroma."""
    if not remove_product(product_id):
        raise HTTPException(status_code=404, detail="Product not found")
