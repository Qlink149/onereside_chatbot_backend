import re
import uuid

from pymongo import ReturnDocument

from onereside_chatbot.database.collections import product
from onereside_chatbot.database.chroma.utils import add_product, update_product_embedding, delete_product as chroma_delete_product, delete_brand_products as chroma_delete_brand_products
from onereside_chatbot.database.storage.r2_utils import delete_media
from onereside_chatbot.utils.env_load import r2_public_url
from onereside_chatbot.utils.logger_config import logger


def _extract_r2_key(url: str) -> str | None:
    """Extract the R2 object key from a public URL."""
    base = r2_public_url.rstrip("/") + "/"
    if url.startswith(base):
        return url[len(base):]
    return None


def _generate_product_id(brand_id: str, category: str) -> str:
    brand_code = re.sub(r"[^A-Za-z0-9]", "", brand_id).upper()[:3]
    category_initials = "".join(w[0] for w in category.split() if w)
    category_code = re.sub(r"[^A-Za-z0-9]", "", category_initials).upper()[:3]
    while True:
        suffix = uuid.uuid4().hex[:6].upper()
        product_id = f"{brand_code}-{category_code}-{suffix}"
        if not product.find_one({"product_id": product_id}, {"_id": 1}):
            return product_id


def get_product_by_id(product_id: str):
    """Get product doc by id."""
    try:
        product_doc = product.find_one(
            {"product_id": product_id},
            {"_id": 0},
        )
        if not product_doc:
            logger.exception(
                "No product found for given id.",
                extra={"product_id": product_id},
            )
            return False
        return product_doc
    except Exception as e:
        logger.exception(
            "Exception occurred while fetching product_id.",
            extra={"product_id": product_id},
        )
        raise e


def get_all_products(
    skip: int = 0,
    limit: int = 20,
    brand_id: str | None = None,
    category: str | None = None,
    listing_type: str | None = None,
    type: str | None = None,
) -> tuple[int, list]:
    """Get paginated list of products with optional filters. Returns (total, products)."""
    try:
        query = {}
        if brand_id:
            query["brand_id"] = brand_id
        if category:
            query["category"] = {"$regex": category, "$options": "i"}
        if listing_type:
            query["listing_type"] = listing_type
        if type:
            query["type"] = type

        projection = {"product_id": 1, "name": 1, "brand_id": 1, "category": 1, "listing_type": 1, "type": 1, "_id": 0}

        total = product.count_documents(query)
        products = list(product.find(query, projection).skip(skip).limit(limit))
        logger.info("Fetched products", extra={"skip": skip, "limit": limit, "total": total, "query": query})
        return total, products
    except Exception as e:
        logger.exception("Exception occurred while fetching products.")
        raise e


def create_product(data: dict) -> dict:
    """Insert a new product into MongoDB and add its description to Chroma."""
    try:
        product_id = _generate_product_id(data["brand_id"], data["category"])
        data["product_id"] = product_id

        product.insert_one(data)
        data.pop("_id", None)

        add_product(data)

        logger.info("Product created successfully.", extra={"product_id": product_id})
        return data
    except Exception as e:
        logger.exception("Exception occurred while creating product.")
        raise e


def update_product(product_id: str, update_data: dict) -> dict | None:
    """Update a product by product_id. Syncs description to Chroma if changed. Cleans up orphaned R2 media."""
    try:
        old_doc = product.find_one({"product_id": product_id}, {"media_url": 1}) if "media_url" in update_data else None

        result = product.find_one_and_update(
            {"product_id": product_id},
            {"$set": update_data},
            return_document=ReturnDocument.AFTER,
        )
        if not result:
            logger.warning("No product found to update.", extra={"product_id": product_id})
            return None

        if old_doc and "media_url" in update_data:
            old_urls = {m.get("url") for m in old_doc.get("media_url", [])}
            new_urls = {m.get("url") for m in update_data["media_url"]}
            for url in old_urls - new_urls:
                key = _extract_r2_key(url)
                if key:
                    delete_media(key)

        _embedding_fields = {"name", "category", "type", "listing_type", "description", "style_tags", "materials", "ideal_for", "colors_available", "deliverables"}
        if update_data.keys() & _embedding_fields:
            update_product_embedding(result)

        result.pop("_id", None)
        logger.info("Product updated successfully.", extra={"product_id": product_id})
        return result
    except Exception as e:
        logger.exception("Exception occurred while updating product.", extra={"product_id": product_id})
        raise e


def remove_product(product_id: str) -> bool:
    """Delete a product from MongoDB, Chroma, and R2. Returns True if found and deleted."""
    try:
        product_doc = product.find_one({"product_id": product_id}, {"media_url": 1})
        result = product.delete_one({"product_id": product_id})
        if result.deleted_count == 0:
            logger.warning("No product found to delete.", extra={"product_id": product_id})
            return False
        chroma_delete_product(product_id)
        for media in (product_doc or {}).get("media_url", []):
            key = _extract_r2_key(media.get("url", ""))
            if key:
                delete_media(key)
        logger.info("Product deleted successfully.", extra={"product_id": product_id})
        return True
    except Exception as e:
        logger.exception("Exception occurred while deleting product.", extra={"product_id": product_id})
        raise e


def remove_products_by_brand(brand_id: str) -> int:
    """Delete all products for a brand from MongoDB, Chroma, and R2. Returns count deleted."""
    try:
        docs = list(product.find({"brand_id": brand_id}, {"product_id": 1, "media_url": 1}))
        if not docs:
            return 0
        product_ids = [d["product_id"] for d in docs]
        product.delete_many({"brand_id": brand_id})
        chroma_delete_brand_products(brand_id)
        for doc in docs:
            for media in doc.get("media_url", []):
                key = _extract_r2_key(media.get("url", ""))
                if key:
                    delete_media(key)
        logger.info("Brand products deleted.", extra={"brand_id": brand_id, "count": len(product_ids)})
        return len(product_ids)
    except Exception as e:
        logger.exception("Exception occurred while deleting brand products.", extra={"brand_id": brand_id})
        raise e


def get_catalog_metadata(brand_id: str = None) -> dict:
    """
    Fetch distinct catalog attributes for prompt injection.
    If brand_id is provided, returns brand-scoped metadata alongside full platform metadata.
    """
    try:
        all_categories = [c for c in product.distinct("category") if c]
        all_style_tags = [s for s in product.distinct("style_tags") if s]
        all_ideal_for = [i for i in product.distinct("ideal_for") if i]
        all_listing_types = [lt for lt in product.distinct("listing_type") if lt]

        if brand_id:
            brand_filter = {"brand_id": brand_id}
            brand_categories = [c for c in product.distinct("category", brand_filter) if c]
            brand_style_tags = [s for s in product.distinct("style_tags", brand_filter) if s]
            brand_ideal_for = [i for i in product.distinct("ideal_for", brand_filter) if i]
            brand_listing_types = [lt for lt in product.distinct("listing_type", brand_filter) if lt]
            return {
                "categories": brand_categories,
                "style_tags": brand_style_tags,
                "ideal_for": brand_ideal_for,
                "listing_types": brand_listing_types,
                "all_categories": all_categories,
                "all_style_tags": all_style_tags,
                "all_ideal_for": all_ideal_for,
                "all_listing_types": all_listing_types,
            }

        return {
            "categories": all_categories,
            "style_tags": all_style_tags,
            "ideal_for": all_ideal_for,
            "listing_types": all_listing_types,
        }
    except Exception as e:
        logger.exception("Failed to fetch catalog metadata.")
        return {"categories": [], "style_tags": [], "ideal_for": []}
