import time

from bson import ObjectId
from pymongo import ReturnDocument, DESCENDING

from onereside_chatbot.database.collections import orders
from onereside_chatbot.utils.logger_config import logger

_LIST_PROJECTION = {
    "phone_number": 1,
    "username": 1,
    "product.product_id": 1,
    "product.name": 1,
    "product.brand_id": 1,
    "amount_inr": 1,
    "payment_status": 1,
    "payment_link_id": 1,
    "created_at": 1,
}


def _build_query(
    payment_status: str | None = None,
    brand_id: str | None = None,
    product_id: str | None = None,
    phone_number: str | None = None,
) -> dict:
    query = {}
    if payment_status:
        query["payment_status"] = payment_status
    if brand_id:
        query["product.brand_id"] = brand_id
    if product_id:
        query["product.product_id"] = product_id
    if phone_number:
        query["phone_number"] = phone_number
    return query


def get_all_orders(
    skip: int = 0,
    limit: int = 20,
    payment_status: str | None = None,
    brand_id: str | None = None,
    product_id: str | None = None,
) -> tuple[int, list]:
    """Get paginated orders with optional filters. Returns (total, orders)."""
    try:
        query = _build_query(payment_status=payment_status, brand_id=brand_id, product_id=product_id)
        total = orders.count_documents(query)
        docs = list(orders.find(query, _LIST_PROJECTION).sort("created_at", DESCENDING).skip(skip).limit(limit))
        for d in docs:
            d["_id"] = str(d["_id"])
        logger.info("Fetched orders", extra={"total": total, "query": query})
        return total, docs
    except Exception as e:
        logger.exception("Exception occurred while fetching orders.")
        raise e


def get_orders_by_phone(phone_number: str, skip: int = 0, limit: int = 20) -> tuple[int, list]:
    """Get paginated orders for a phone number. Returns (total, orders)."""
    try:
        query = _build_query(phone_number=phone_number)
        total = orders.count_documents(query)
        docs = list(orders.find(query, _LIST_PROJECTION).sort("created_at", DESCENDING).skip(skip).limit(limit))
        for d in docs:
            d["_id"] = str(d["_id"])
        return total, docs
    except Exception as e:
        logger.exception("Exception occurred while fetching orders by phone.", extra={"phone_number": phone_number})
        raise e


def get_orders_by_product(product_id: str, skip: int = 0, limit: int = 20) -> tuple[int, list]:
    """Get paginated orders for a product_id. Returns (total, orders)."""
    try:
        query = {"product.product_id": product_id}
        total = orders.count_documents(query)
        docs = list(orders.find(query, _LIST_PROJECTION).sort("created_at", DESCENDING).skip(skip).limit(limit))
        for d in docs:
            d["_id"] = str(d["_id"])
        return total, docs
    except Exception as e:
        logger.exception("Exception occurred while fetching orders by product.", extra={"product_id": product_id})
        raise e


def get_orders_by_brand(brand_id: str, skip: int = 0, limit: int = 20) -> tuple[int, list]:
    """Get paginated orders for a brand_id. Returns (total, orders)."""
    try:
        query = {"product.brand_id": brand_id}
        total = orders.count_documents(query)
        docs = list(orders.find(query, _LIST_PROJECTION).sort("created_at", DESCENDING).skip(skip).limit(limit))
        for d in docs:
            d["_id"] = str(d["_id"])
        return total, docs
    except Exception as e:
        logger.exception("Exception occurred while fetching orders by brand.", extra={"brand_id": brand_id})
        raise e


def get_order_by_id(order_id: ObjectId) -> dict | None:
    """Get full order details by MongoDB ObjectId."""
    try:
        doc = orders.find_one({"_id": order_id})
        if not doc:
            return None
        doc["_id"] = str(doc["_id"])
        return doc
    except Exception as e:
        logger.exception("Exception occurred while fetching order.", extra={"order_id": str(order_id)})
        raise e


def save_order(order_data: dict) -> str:
    """Save a new order to the orders collection. Returns the inserted order _id as string."""
    try:
        order_data["created_at"] = int(time.time())
        order_data["updated_at"] = int(time.time())
        result = orders.insert_one(order_data)
        logger.info(
            "Order saved successfully",
            extra={"inserted_id": str(result.inserted_id)},
        )
        return str(result.inserted_id)
    except Exception as e:
        logger.exception("Failed to save order.", extra={"exception": e})
        raise e


def update_order_by_payment_link_id(payment_link_id: str, update_data: dict) -> dict | None:
    """Find an order by payment_link_id and update it."""
    try:
        update_data["updated_at"] = int(time.time())
        result = orders.find_one_and_update(
            {"payment_link_id": payment_link_id},
            {"$set": update_data},
            return_document=ReturnDocument.AFTER,
        )
        if result:
            result.pop("_id", None)
            logger.info(
                "Order updated by payment_link_id successfully",
                extra={"payment_link_id": payment_link_id},
            )
        else:
            logger.warning(
                "No order found with given payment_link_id",
                extra={"payment_link_id": payment_link_id},
            )
        return result
    except Exception as e:
        logger.exception(
            "Failed to update order by payment_link_id.",
            extra={"exception": e, "payment_link_id": payment_link_id},
        )
        raise e


def update_order_by_payment_id(payment_id: str, update_data: dict) -> dict | None:
    """Find an order by razorpay_payment_id and update it."""
    try:
        update_data["updated_at"] = int(time.time())
        result = orders.find_one_and_update(
            {"razorpay_payment_id": payment_id},
            {"$set": update_data},
            return_document=ReturnDocument.AFTER,
        )
        if result:
            result.pop("_id", None)
            logger.info(
                "Order updated successfully",
                extra={"payment_id": payment_id},
            )
        else:
            logger.warning(
                "No order found with given payment_id",
                extra={"payment_id": payment_id},
            )
        return result
    except Exception as e:
        logger.exception(
            "Failed to update order.",
            extra={"exception": e, "payment_id": payment_id},
        )
        raise e
