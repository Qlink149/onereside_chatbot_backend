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


def add_product(product_id: str, description: str, brand_id: str, category: str):
    """
    Add a product's description to the vector collection.
    Called when a new product is added to MongoDB.
    """
    try:
        product_collection.add(
            ids=[product_id],
            documents=[description],
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