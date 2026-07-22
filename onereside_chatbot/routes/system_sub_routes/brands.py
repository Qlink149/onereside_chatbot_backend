import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from onereside_chatbot.database.brand_utils import (
    create_brand,
    get_all_brands,
    get_brand_by_id,
    get_brands_summary,
    remove_brand,
    update_brand,
)
from onereside_chatbot.database.product_utils import remove_products_by_brand
from onereside_chatbot.database.storage.r2_utils import upload_media
from onereside_chatbot.routes.dependencies import verify_api_key

router = APIRouter(prefix="/brands", tags=["brands"])

CATALOGUE_CONTENT_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}


class BrandCreate(BaseModel):
    brand_name: str
    brand_description: str
    brand_short_pitch: str
    categories_offered: list[str]
    has_ready_products: bool = False
    has_custom_products: bool = False
    has_services: bool = False
    working_hours: str
    catalogue_url: str | None = None
    brand_additional_context: str = ""


class BrandUpdate(BaseModel):
    brand_name: str | None = None
    brand_description: str | None = None
    brand_short_pitch: str | None = None
    categories_offered: list[str] | None = None
    has_ready_products: bool | None = None
    has_custom_products: bool | None = None
    has_services: bool | None = None
    working_hours: str | None = None
    catalogue_url: str | None = None
    brand_additional_context: str | None = None


@router.post("", status_code=201)
def add_brand(body: BrandCreate, _: str = Depends(verify_api_key)):
    """Create a new brand. brand_id is auto-generated from brand_name."""
    return create_brand(body.model_dump())


@router.get("/summary")
def list_brands_summary(_: str = Depends(verify_api_key)):
    """Get brand_id and brand_name for all brands (for dropdowns)."""
    return get_brands_summary()


@router.get("")
def list_brands(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _: str = Depends(verify_api_key),
):
    """List all brands with pagination."""
    skip = (page - 1) * limit
    total, brands = get_all_brands(skip=skip, limit=limit)
    return {"total": total, "page": page, "limit": limit, "data": brands}


@router.get("/{brand_id}")
def get_brand(brand_id: str, _: str = Depends(verify_api_key)):
    """Get a brand by brand_id."""
    brand = get_brand_by_id(brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    return brand


@router.patch("/{brand_id}")
def patch_brand(brand_id: str, body: BrandUpdate, _: str = Depends(verify_api_key)):
    """Update brand details. brand_id cannot be changed."""
    update_data = body.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    updated = update_brand(brand_id, update_data)
    if not updated:
        raise HTTPException(status_code=404, detail="Brand not found")
    return updated


@router.post("/catalogue/upload", status_code=201)
async def upload_catalogue(
    file: UploadFile = File(...),
    _: str = Depends(verify_api_key),
):
    """Upload a brand catalogue or brochure to R2. Returns the URL to store on the brand."""
    if file.content_type not in CATALOGUE_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}")
    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "pdf"
    key = f"brands/catalogues/{uuid.uuid4().hex}.{ext}"
    url = upload_media(file.file, key, file.content_type)
    return {"url": url}


@router.delete("/{brand_id}", status_code=204)
def delete_brand(brand_id: str, _: str = Depends(verify_api_key)):
    """Delete a brand and all its associated products."""
    if not remove_brand(brand_id):
        raise HTTPException(status_code=404, detail="Brand not found")
    remove_products_by_brand(brand_id)
