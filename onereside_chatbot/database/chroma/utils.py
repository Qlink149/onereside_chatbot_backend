import uuid

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
from onereside_chatbot.constants import TEXT_EMBEDDING_MODEL
from onereside_chatbot.utils.env_load import chorma_tenant, chroma_api, openai_api_key
from onereside_chatbot.utils.logger_config import logger


chromaClient = chromadb.CloudClient(
    tenant=chorma_tenant,
    database="OneReside",
    api_key=chroma_api
)

product_collection = chromaClient.get_collection(
    name="product",
    embedding_function=OpenAIEmbeddingFunction(
        api_key=openai_api_key,
        model_name=TEXT_EMBEDDING_MODEL
    )
)


def generate_id():
    """Generate a short unique ID."""
    return f"{uuid.uuid4().hex[:8]}"


def build_search_text(product: dict) -> str:
    """Build a rich text blob for embedding from multiple product fields."""
    parts = [
        product.get("name", ""),
        product.get("category", ""),
        product.get("type", ""),
        product.get("description", ""),
        ", ".join(product.get("style_tags", [])),
        ", ".join(product.get("materials", [])),
        ", ".join(product.get("ideal_for", [])),
        ", ".join(product.get("colors_available", [])),
    ]
    return " | ".join(p for p in parts if p)


def add_product(product: dict):
    """
    Add a product to the vector collection using a rich text embedding.
    Called when a new product is added to MongoDB.
    """
    product_id = product["product_id"]
    brand_id = product["brand_id"]
    category = product["category"]
    try:
        product_collection.add(
            ids=[product_id],
            documents=[build_search_text(product)],
            metadatas=[{
                "brand_id": brand_id,
                "category": category,
                "product_id": product_id
            }]
        )

        logger.info(
            "Product added to vector DB.",
            extra={"product_id": product_id, "brand_id": brand_id}
        )
    except Exception as e:
        logger.error(
            "Error adding product to vector DB.",
            extra={"product_id": product_id, "error": e}
        )
        raise e


def semantic_search(
    query: str,
    brand_ids: list = None,
    exclude_ids: list = None,
    n_results: int = 3
):
    """
    Search products by semantic similarity.
    Pass brand_ids to scope to specific brands; omit (or pass None) to search all brands.
    Returns list of matching product IDs.
    """
    try:
        where_clause = {"brand_id": {"$in": brand_ids}} if brand_ids else None

        response = product_collection.query(
            query_texts=[query],
            where=where_clause,
            n_results=n_results
        )

        product_ids = []

        if response and response.get("ids"):
            for pid in response["ids"][0]:
                if exclude_ids and pid in exclude_ids:
                    continue
                product_ids.append(pid)

        logger.info(
            "Semantic search completed.",
            extra={
                "query": query,
                "brand_ids": brand_ids,
                "results": product_ids
            }
        )

        return product_ids

    except Exception as e:
        logger.error(
            "Error during semantic search.",
            extra={"query": query, "brand_ids": brand_ids, "error": e}
        )
        raise e


def update_product_embedding(product: dict):
    """Update a product's embedding in the vector DB using the full product data."""
    product_id = product["product_id"]
    try:
        product_collection.update(
            ids=[product_id],
            documents=[build_search_text(product)],
        )
        logger.info(
            "Product embedding updated in vector DB.",
            extra={"product_id": product_id}
        )
    except Exception as e:
        logger.error(
            "Error updating product embedding in vector DB.",
            extra={"product_id": product_id, "error": e}
        )
        raise e


def delete_brand_products(brand_id: str):
    """Delete all product vectors for a brand."""
    try:
        product_collection.delete(where={"brand_id": brand_id})
        logger.info(
            "Deleted brand products from vector DB.",
            extra={"brand_id": brand_id}
        )
    except Exception as e:
        logger.error(
            "Error deleting brand products from vector DB.",
            extra={"brand_id": brand_id, "error": e}
        )
        raise e


def delete_product(product_id: str):
    """Delete a single product from vector DB."""
    try:
        product_collection.delete(ids=[product_id])
        logger.info(
            "Deleted product from vector DB.",
            extra={"product_id": product_id}
        )
    except Exception as e:
        logger.error(
            "Error deleting product from vector DB.",
            extra={"product_id": product_id, "error": e}
        )
        raise e