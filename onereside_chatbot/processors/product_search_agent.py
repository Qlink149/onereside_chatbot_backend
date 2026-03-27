from onereside_chatbot.processors.abstract_processor import Processor
from onereside_chatbot.utils.logger_config import logger
from onereside_chatbot.prompt.product_search import (
    build_product_presenter_prompt,
    build_product_recommender_prompt,
    output_schema,
    presenter_output_schema,
    search_products_tool,
    get_product_by_id_tool,
    compare_products_tool,
)
from onereside_chatbot.utils.get_openai_client import openai_client
from onereside_chatbot.database.collections import product as pd
from onereside_chatbot.database.chroma.utils import semantic_search
from onereside_chatbot.database.db_utils import get_product_by_id, get_brands_by_ids, get_catalog_metadata
from onereside_chatbot.whatsapp_functions.send_text_message import send_text_message

import json
import random


# Fields sent to the presenter not full docs
PRESENTER_FIELDS = {
    "product_id", "name", "price_inr", "brand_id", "brand_name", "category",
    "style_tags", "ideal_for", "materials", "colors_available",
    "description", "delivery_timeline",
}


def _trim_for_presenter(products: list) -> list:
    return [{k: v for k, v in p.items() if k in PRESENTER_FIELDS} for p in products]


class ProductAgent(Processor):
    """Search a product search Query."""

    def should_run(self, data: dict) -> bool:
        if "bot_response" in data:
            return False
        return True

    def handle_search(self, args: dict, exclude_ids: list) -> list:
        """
        Single search handler.
        - Semantic search with optional price / category post-filtering.
        - If brand_id is passed but returns no results, auto-fallback to all brands.
        """
        try:
            query = args.get("query", "")
            brand_id = args.get("brand_id")
            price_min = args.get("price_min") or 0
            price_max = args.get("price_max") or 0
            category = args.get("category")

            # Wider pool when price/category filters will be applied post-search
            has_filters = price_min > 0 or (0 < price_max < 10_000_000) or category
            n_results = 15 if has_filters else 5

            def fetch_products(product_ids: list) -> list:
                if not product_ids:
                    return []
                # Exclude already-shown IDs before hitting Mongo
                filtered_ids = [pid for pid in product_ids if pid not in exclude_ids]
                if not filtered_ids:
                    return []

                q = {"product_id": {"$in": filtered_ids}}
                if price_min > 0 or (0 < price_max < 10_000_000):
                    price_filter = {}
                    if price_min > 0:
                        price_filter["$gte"] = price_min
                    if 0 < price_max < 10_000_000:
                        price_filter["$lte"] = price_max
                    q["$or"] = [
                        {"price_inr": price_filter},
                        {"price_inr": None},
                    ]
                # Fetch all matches, then re-sort by semantic relevance order and take top 3
                # MongoDB $in does NOT preserve order — without this, irrelevant products surface first
                order = {pid: i for i, pid in enumerate(filtered_ids)}
                docs = list(pd.find(q, {"_id": 0, "media_url": 0}))
                docs.sort(key=lambda p: order.get(p["product_id"], 999))
                return docs[:3]

            # Step 1: search within brand (if brand_id provided)
            product_ids = semantic_search(
                query=query,
                brand_ids=[brand_id] if brand_id else None,
                n_results=n_results,
            )
            products = fetch_products(product_ids)

            # Step 2: cross-brand fallback — brand had no match
            if not products and brand_id:
                logger.info(
                    "Brand search returned no results, falling back to all brands",
                    extra={"brand_id": brand_id, "query": query},
                )
                product_ids = semantic_search(query=query, brand_ids=None, n_results=n_results)
                products = fetch_products(product_ids)

            logger.info(
                "Search completed",
                extra={"query": query, "brand_id": brand_id, "results": [p.get("product_id") for p in products]},
            )
            return products

        except Exception as e:
            logger.error("Error in handle_search", extra={"error": e})
            return []

    async def process(self, data: dict) -> dict:
        phone_number = data["phone_number"]
        user_profile = data["user_profile"]
        username = user_profile["username"]
        brand = data.get("brand")

        if not self.should_run(data):
            logger.info(
                "Skipping processor",
                extra={"processor": self.__class__.__name__, "phone_number": phone_number},
            )
            return data

        try:
            if "text" in data["messages"]:
                user_query = data["messages"]["text"]["body"]
                shown_products = user_profile.get("shown_products", [])
                exclude_ids = [p["product_id"] for p in shown_products[-5:]] if shown_products else []

                # Fetch catalog metadata for prompt injection
                catalog_metadata = get_catalog_metadata()

                # Build prompts
                product_recommender_prompt = build_product_recommender_prompt(
                    brand=brand,
                    catalog_metadata=catalog_metadata,
                )
                product_presenter_prompt = build_product_presenter_prompt()

                # Chat history
                chat_history = user_profile.get("chat_history", [])[-10:]
                chat_history_str = "\n".join(
                    f"{c.get('role','').capitalize()}: {c.get('content','')}"
                    for c in chat_history
                )

                shown_products_summary = (
                    json.dumps([{"product_id": p["product_id"], "name": p["name"]} for p in shown_products[-10:]])
                    if shown_products else "[]"
                )

                messages = [
                    {"role": "system", "content": f"Username: {username}"},
                    {"role": "system", "content": f"Recent chat history:\n{chat_history_str}"},
                    {"role": "system", "content": f"Last Shown Product: {user_profile.get('last_shown_product', '')}"},
                    {"role": "system", "content": f"All previously shown products (use product_id to fetch any of them): {shown_products_summary}"},
                    {"role": "user", "content": user_query},
                ]

                # Recommender loop — max 2 search iterations for self-correction
                MAX_SEARCH_ITERATIONS = 2
                iteration = 0
                products = []
                is_new_topic = False
                is_reshow = False
                is_comparison = False
                tool_call = None
                text_message = None
                current_messages = messages

                while iteration < MAX_SEARCH_ITERATIONS:
                    response = await openai_client.responses.create(
                        model="gpt-5-mini",
                        instructions=product_recommender_prompt,
                        input=current_messages,
                        tools=[search_products_tool, get_product_by_id_tool, compare_products_tool],
                        tool_choice="auto",
                        parallel_tool_calls=False,
                        text=output_schema,
                        max_output_tokens=2000,
                    )

                    logger.info(
                        "Recommender response",
                        extra={"response": response.model_dump(), "phone_number": phone_number, "iteration": iteration + 1},
                    )

                    tool_call = None
                    text_message = None

                    for item in response.output:
                        if item.type == "function_call":
                            tool_call = item
                        elif item.type == "message":
                            text_message = item

                    # If the model wrote a conversational message, show it — even if it also made a tool call
                    if text_message:
                        break

                    # Tool call detected on first pass — ack before the slow search
                    if iteration == 0:
                        _ack_messages = ["On it! 🔍", "Give me a sec...", "Let me look that up 👀"]
                        send_text_message(phone_number, {"type": "text", "text": random.choice(_ack_messages)})

                    args = json.loads(tool_call.arguments)
                    is_new_topic = args.get("is_new_topic", False)

                    logger.info("Tool invoked", extra={"tool": tool_call.name, "arguments": args, "iteration": iteration + 1})

                    if tool_call.name == "compare_products":
                        p1 = get_product_by_id(product_id=args["product_id_1"])
                        p2 = get_product_by_id(product_id=args["product_id_2"])
                        products = [p for p in [p1, p2] if p]
                        is_comparison = True
                        iteration += 1
                        break  # direct fetch — no need to loop

                    if tool_call.name == "get_product_by_id":
                        product = get_product_by_id(product_id=args["product_id"])
                        products = [product] if product else []
                        is_reshow = True
                        iteration += 1
                        break  # direct fetch — no need to loop

                    products = self.handle_search(args, exclude_ids)
                    iteration += 1

                    if len(products) >= 2 or iteration >= MAX_SEARCH_ITERATIONS:
                        break

                    # Feed back only count + hint — never product details, to prevent recommender hallucination
                    current_messages = current_messages + list(response.output) + [
                        {
                            "type": "function_call_output",
                            "call_id": tool_call.call_id,
                            "output": json.dumps({
                                "results_count": len(products),
                                "hint": "Too few results — try a broader query or drop the category/brand_id filter to widen the search." if len(products) < 2 else "ok",
                            }),
                        }
                    ]

                if tool_call:
                    # Enrich with brand_name
                    unique_brand_ids = list({p["brand_id"] for p in products if p.get("brand_id")})
                    if unique_brand_ids:
                        brand_map = {b["brand_id"]: b["brand_name"] for b in get_brands_by_ids(unique_brand_ids)}
                        for p in products:
                            p["brand_name"] = brand_map.get(p.get("brand_id"), "")

                    logger.info(
                        "Search results",
                        extra={"products": json.dumps(_trim_for_presenter(products))},
                    )

                    # Build shown history summary for presenter context
                    shown_summary = (
                        "Previously shown to this customer: " + ", ".join(p["name"] for p in shown_products[-5:])
                        if shown_products else "Nothing shown yet."
                    )

                    # Presenter call — trimmed docs only
                    scanned_brand_name = brand.get("brand_name", "") if brand else "None"
                    presenter_messages = [
                        {"role": "system", "content": f"Username: {username}"},
                        {"role": "system", "content": f"Customer's scanned brand: {scanned_brand_name}"},
                        {"role": "system", "content": f"Recent chat history:\n{chat_history_str}"},
                        {"role": "system", "content": f"Search results: {json.dumps(_trim_for_presenter(products))}"},
                        {"role": "system", "content": f"Last Shown Product: {user_profile.get('last_shown_product', '')}"},
                        {"role": "system", "content": shown_summary},
                        {"role": "system", "content": f"Is new topic: {is_new_topic}. {'Treat this as a fresh first recommendation — ignore prior rejections in chat history.' if is_new_topic else ''}"},
                        {"role": "system", "content": f"Is re-show: {is_reshow}. {'The customer asked to see this product again — show it as requested, acknowledge it naturally.' if is_reshow else ''}"},
                        {"role": "system", "content": f"Is comparison: {is_comparison}. {'The customer wants to compare both products — write a side-by-side comparison message, set product_ids to both IDs, and set product_id to null.' if is_comparison else ''}"},
                        {"role": "user", "content": user_query},
                    ]

                    presenter_response = await openai_client.responses.create(
                        model="gpt-4o-mini",
                        instructions=product_presenter_prompt,
                        input=presenter_messages,
                        text=presenter_output_schema,
                        max_output_tokens=400,
                    )

                    logger.info(
                        "Presenter response",
                        extra={"response": presenter_response.model_dump(), "phone_number": phone_number},
                    )

                    presenter_output_text = presenter_response.output[0].content[0].text
                    presenter_output = json.loads(presenter_output_text)

                    bot_response = []

                    if presenter_output.get("product_ids"):
                        # Comparison mode — show both products' media, one combined message at the end
                        for pid in presenter_output["product_ids"]:
                            product = get_product_by_id(product_id=pid)
                            if not product:
                                continue
                            user_profile.setdefault("shown_products", []).append({
                                "product_id": pid,
                                "name": product.get("name", ""),
                            })
                            if product.get("media_url"):
                                for urls in product.get("media_url", []):
                                    bot_response.append(
                                        {
                                            "type": "media",
                                            "media_type": urls.get("type"),
                                            "url": urls.get("url"),
                                            "caption": product.get("name"),
                                            "filename": product.get("name"),
                                        }
                                    )
                        bot_response.append(
                            {
                                "type": "text",
                                "text": presenter_output.get("message", ""),
                            }
                        )

                    elif presenter_output.get("product_id"):
                        product = get_product_by_id(product_id=presenter_output["product_id"])

                        if product:
                            user_profile.setdefault("shown_products", []).append({
                                "product_id": presenter_output["product_id"],
                                "name": product.get("name", ""),
                            })

                            if product.get("media_url"):
                                for urls in product.get("media_url", []):
                                    bot_response.append(
                                        {
                                            "type": "media",
                                            "media_type": urls.get("type"),
                                            "url": urls.get("url"),
                                            "caption": product.get("name"),
                                            "filename": product.get("name"),
                                        }
                                    )

                            user_profile["last_shown_product"] = json.dumps(product)

                            if presenter_output.get("show_cta"):
                                bot_response.append(
                                    {
                                        "type": "quickreply",
                                        "text": presenter_output.get("message", ""),
                                        "caption": "Click the cta to buy the product.",
                                        "options": [{"title": "Buy"}],
                                        "msgid": f"buy${presenter_output['product_id']}",
                                    }
                                )
                            else:
                                bot_response.append(
                                    {
                                        "type": "text",
                                        "text": presenter_output.get("message", ""),
                                    }
                                )
                    else:
                        bot_response.append(
                            {
                                "type": "text",
                                "text": presenter_output.get("message", ""),
                            }
                        )

                    data["bot_response"] = bot_response
                    user_profile["service_selected"] = ""
                    return data

                else:
                    # Recommender asked a clarifying question (no tool call, has message)
                    if not text_message:
                        logger.warning("Recommender returned no message and no tool call", extra={"phone_number": phone_number})
                        data["bot_response"] = [{"type": "text", "text": "Give me a sec, let me look that up for you."}]
                        user_profile["service_selected"] = ""
                        return data

                    output_text = text_message.content[0].text
                    output = json.loads(output_text)

                    data["bot_response"] = [{"type": "text", "text": output.get("message", "")}]
                    user_profile["service_selected"] = ""
                    return data

        except Exception as e:
            logger.exception("Exception occurred in ProductAgent")
            raise e
