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
    search_brand_tool,
)
from onereside_chatbot.utils.get_openai_client import openai_client
from onereside_chatbot.database.collections import product as pd
from onereside_chatbot.database.chroma.utils import semantic_search, semantic_brand_search
from onereside_chatbot.database.brand_utils import get_brand_by_id
from onereside_chatbot.database.db_utils import get_product_by_id, get_brands_by_ids, get_catalog_metadata
from onereside_chatbot.whatsapp_functions.send_text_message import send_text_message
from onereside_chatbot.constants import ACK_MESSAGES

import json
import random


# Fields sent to the presenter not full docs
PRESENTER_FIELDS = {
    "product_id", "name", "price_inr", "brand_id", "brand_name", "category",
    "listing_type", "style_tags", "ideal_for", "materials", "colors_available",
    "description", "delivery_timeline",
}


def _trim_for_presenter(products: list) -> list:
    return [{k: v for k, v in p.items() if k in PRESENTER_FIELDS} for p in products]


def _apply_needs_update(user_profile: dict, output: dict) -> None:
    """Merge add_needs / remove_needs from an LLM output into user_profile["pending_needs"]."""
    pending: list = list(user_profile.get("pending_needs", []))
    existing_lower = {n.lower() for n in pending}

    for need in output.get("add_needs", []):
        if need.lower() not in existing_lower:
            pending.append(need)
            existing_lower.add(need.lower())

    remove_lower = {n.lower() for n in output.get("remove_needs", [])}
    pending = [n for n in pending if n.lower() not in remove_lower]

    user_profile["pending_needs"] = pending


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
            listing_type = args.get("listing_type") or None
            if listing_type == "all":
                listing_type = None

            # Wider pool when price/category filters will be applied post-search
            has_filters = price_min > 0 or (0 < price_max < 10_000_000) or category
            n_results = 15

            def fetch_products(product_ids: list) -> list:
                if not product_ids:
                    return []
                # Exclude already-shown IDs before hitting Mongo
                filtered_ids = [pid for pid in product_ids if pid not in exclude_ids]
                if not filtered_ids:
                    return []

                q = {"product_id": {"$in": filtered_ids}}
                if category:
                    q["category"] = {"$regex": category, "$options": "i"}
                if listing_type:
                    q["listing_type"] = listing_type
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
                return docs

            # Step 1: search within brand (if brand_id provided)
            product_ids = semantic_search(
                query=query,
                brand_ids=[brand_id] if brand_id else None,
                n_results=n_results,
                listing_type=listing_type,
            )
            products = fetch_products(product_ids)

            # Step 2: cross-brand fallback — brand had no match
            if not products and brand_id:
                logger.info(
                    "Brand search returned no results, falling back to all brands",
                    extra={"brand_id": brand_id, "query": query},
                )
                product_ids = semantic_search(query=query, brand_ids=None, n_results=n_results, listing_type=listing_type)
                products = fetch_products(product_ids)

            logger.info(
                "Search completed",
                extra={"query": query, "brand_id": brand_id, "listing_type": listing_type, "results": [p.get("product_id") for p in products], "category": category},
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
        requested_brand = user_profile.get("requested_brand")  # brand user asked for in a prior turn

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

                # Fetch catalog metadata for prompt injection (brand-scoped when available)
                catalog_metadata = get_catalog_metadata(brand_id=brand.get("brand_id") if brand else None)

                # Build prompts
                product_recommender_prompt = build_product_recommender_prompt(
                    brand=brand,
                    catalog_metadata=catalog_metadata,
                )
                product_presenter_prompt = build_product_presenter_prompt()

                # Chat history
                chat_history = user_profile.get("chat_history", [])[-24:]

                shown_products_summary = (
                    json.dumps([{"product_id": p["product_id"], "name": p["name"]} for p in shown_products[-10:]])
                    if shown_products else "[]"
                )

                pending_needs = user_profile.get("pending_needs", [])
                pending_needs_str = json.dumps(pending_needs) if pending_needs else "[]"

                def build_history_turns(history: list) -> list:
                    turns = []
                    for c in history:
                        role = c.get("role", "")
                        text = c.get("content", "") or ""
                        if role == "user":
                            turns.append({"role": "user", "content": [{"type": "input_text", "text": text}]})
                        elif role == "assistant":
                            turns.append({"role": "assistant", "content": [{"type": "output_text", "text": text}]})
                    return turns

                messages = [
                    {"role": "system", "content": f"Username: {username}"},
                    {"role": "system", "content": f"Last Shown Product: {user_profile.get('last_shown_product', '')}"},
                    {"role": "system", "content": f"All previously shown products (use product_id to fetch any of them): {shown_products_summary}"},
                    {"role": "system", "content": f"Pending needs (items user wants but hasn't resolved yet): {pending_needs_str}"},
                    {"role": "system", "content": (
                        f"Active brand from this conversation: {requested_brand['brand_name']} (brand_id: {requested_brand['brand_id']}). "
                        f"When the user's message doesn't mention a specific brand, search within this brand first. "
                        f"Fall back cross-brand only if this brand returns no results. "
                        f"Override only when the user explicitly names a different brand or asks for cross-brand options."
                    ) if requested_brand else ""},
                    *build_history_turns(chat_history),
                    {"role": "user", "content": [{"type": "input_text", "text": user_query}]},
                ]

                # Recommender loop — max 2 search iterations for self-correction
                MAX_SEARCH_ITERATIONS = 3
                iteration = 0
                products = []
                is_new_topic = False
                is_reshow = False
                is_comparison = False
                tool_call = None
                text_message = None
                category = ""
                brand_id = ""
                brand_name = ""
                listing_type_searched = ""
                current_messages = messages
                brand_search_done = False  # guard: search_brand must not consume search iterations
                ack_sent = False

                while iteration < MAX_SEARCH_ITERATIONS:
                    response = await openai_client.responses.create(
                        model="gpt-5.2",
                        instructions=product_recommender_prompt,
                        input=current_messages,
                        tools=[search_products_tool, get_product_by_id_tool, compare_products_tool, search_brand_tool],
                        tool_choice="auto",
                        parallel_tool_calls=False,
                        text=output_schema,
                       # temperature = 0.6,
                        max_output_tokens=1200,
                        reasoning={"effort": "low"} 
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

                    # No tool call — model responded directly, exit loop
                    if tool_call is None:
                        break

                    # Tool call present — ignore any text in the same response
                    text_message = None

                    # Ack once per user message — guard against double-send when search_brand precedes search_products
                    if not ack_sent:
                        send_text_message(phone_number, {"type": "text", "text": random.choice(ACK_MESSAGES)})
                        ack_sent = True

                    args = json.loads(tool_call.arguments)
                    is_new_topic = args.get("is_new_topic", False)
                    if tool_call.name == "search_products":
                        category = args.get("category", "")
                        brand_id = args.get("brand_id", "")
                        listing_type_searched = args.get("listing_type", "")

                    logger.info("Tool invoked", extra={"tool": tool_call.name, "arguments": args, "iteration": iteration + 1})

                    if tool_call.name == "search_brand":
                        if brand_search_done:
                            # LLM called search_brand a second time — it already has brand info.
                            # Break so the presenter handles the (empty) state rather than looping.
                            break
                        brand_search_done = True
                        query = args.get("query", "")
                        results = semantic_brand_search(query, n_results=3)
                        if results:
                            # Full doc for top match (includes description)
                            top = get_brand_by_id(results[0]["brand_id"])
                            if top:
                                brand_name = top.get("brand_name", "")
                                brand_id = top.get("brand_id", "")
                            # All chunks from Chroma including embedded search_text
                            all_chunks = [
                                {
                                    "brand_id": r.get("brand_id"),
                                    "brand_name": r.get("brand_name"),
                                    "categories_offered": r.get("categories_offered", "").split(", ") if r.get("categories_offered") else [],
                                    "product_types": r.get("product_types", "").split(", ") if r.get("product_types") else [],
                                    "description": r.get("search_text", ""),
                                }
                                for r in results
                            ]
                            brand_result = {
                                "found": True,
                                "top_match": {
                                    "brand_id": top.get("brand_id"),
                                    "brand_name": top.get("brand_name"),
                                    "brand_description": top.get("brand_description"),
                                    "categories_offered": top.get("categories_offered", []),
                                    "product_types": top.get("product_types", []),
                                    "listing_types": top.get("listing_types", []),
                                    "brand_additional_context": top.get("brand_additional_context", ""),
                                },
                                "all_chunks": all_chunks,
                            } if top else {"found": False}
                        else:
                            brand_result = {"found": False}

                        current_messages = current_messages + list(response.output) + [
                            {
                                "type": "function_call_output",
                                "call_id": tool_call.call_id,
                                "output": json.dumps(brand_result),
                            }
                        ]
                        # Do NOT increment iteration — brand lookup is free and must not
                        # consume one of the two product-search attempts.
                        continue

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

                    # Feed back count + categories found — never product details, to prevent recommender hallucination
                    categories_found = list({p.get("category", "") for p in products if p.get("category")})
                    current_messages = current_messages + list(response.output) + [
                        {
                            "type": "function_call_output",
                            "call_id": tool_call.call_id,
                            "output": json.dumps({
                                "results_count": len(products),
                                "categories_found": categories_found,
                                "hint": "Too few results — try a broader query or drop the category/brand_id filter to widen the search." if len(products) < 2 else "ok",
                            }),
                        }
                    ]

                if brand_name and brand_id:
                    user_profile["requested_brand"] = {"brand_id": brand_id, "brand_name": brand_name}

                if tool_call or products:
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
                        "Previously shown to this customer: " + ", ".join(
                            f"{p['name']} ({p.get('category', 'unknown category')})" for p in shown_products[-5:]
                        )
                        if shown_products else "Nothing shown yet."
                    )

                    # Presenter call — trimmed docs only
                    qr_brand_name = brand.get("brand_name", "") if brand else ""
                    # Resolve brand_name if search_brand tool wasn't called (priority: requested > QR > DB)
                    if not brand_name:
                        if requested_brand and brand_id == requested_brand.get("brand_id", ""):
                            brand_name = requested_brand.get("brand_name", "")
                        elif brand and brand_id == brand.get("brand_id", ""):
                            brand_name = qr_brand_name
                        elif brand_id:
                            lookup = get_brand_by_id(brand_id)
                            brand_name = lookup.get("brand_name", "") if lookup else ""

                    presenter_messages = [
                        {"role": "system", "content": f"Username: {username}"},
                        {"role": "system", "content": f"Customer's scanned brand: {qr_brand_name}"},
                        {"role": "system", "content": f"Category searched for: {category}" if category else ""},
                        {"role": "system", "content": f"Listing type searched for: {listing_type_searched}" if listing_type_searched else "Listing type: not filtered (mixed results possible — label each result's type)"},
                        {"role": "system", "content": f"User explicitly requested brand: {brand_name}" if brand_name else ""},
                        {"role": "system", "content": (
                            f"Brand requested in this search: {brand_name} (brand_id: {brand_id}). "
                            f"Only show a product whose brand_id matches '{brand_id}' exactly. "
                            f"If none of the search results match — do not show any product. "
                        ) if brand_id else ""},
                        {"role": "system", "content": f"Search results: {json.dumps(_trim_for_presenter(products))}"},
                        {"role": "system", "content": f"Important: Last Shown Product: {user_profile.get('last_shown_product', '')}"},
                        {"role": "system", "content": shown_summary},
                        {"role": "system", "content": f"Is new topic: {is_new_topic}. {'Treat this as a fresh first recommendation — ignore prior rejections in chat history.' if is_new_topic else ''}"},
                        {"role": "system", "content": f"Is re-show: {is_reshow}. {'The customer asked to see this product again — show it as requested, acknowledge it naturally.' if is_reshow else ''}"},
                        {"role": "system", "content": f"Is comparison: {is_comparison}. {'The customer wants to compare both products — write a side-by-side comparison message, set product_ids to both IDs, and set product_id to null.' if is_comparison else ''}"},
                        *build_history_turns(chat_history),
                        {"role": "user", "content": [{"type": "input_text", "text": user_query}]},
                    ]

                    presenter_response = await openai_client.responses.create(
                        model="gpt-5.2",
                        instructions=product_presenter_prompt,
                        input=presenter_messages,
                        # temperature=1,
                        text=presenter_output_schema,
                        max_output_tokens=1000,
                        reasoning={"effort": "low"} 
                    )

                    logger.info(
                        "Presenter response",
                        extra={"response": presenter_response.model_dump(), "phone_number": phone_number},
                    )

                    presenter_output_text = next(
                        item.content[0].text
                        for item in presenter_response.output
                        if item.type == "message"
                    )
                    presenter_output = json.loads(presenter_output_text)

                    _apply_needs_update(user_profile, presenter_output)

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
                                "category": product.get("category", ""),
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
                                "category": product.get("category", ""),
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

                            # scanned brand exit strategy
                            scanned_brand_id = brand.get("brand_id", "") if brand else ""
                            if scanned_brand_id and product.get("brand_id") != scanned_brand_id:
                                user_profile["past_brand"] = scanned_brand_id
                                user_profile["current_brand"] = ""
                                user_profile["requested_brand"] = None

                            product_category = (product.get("category") or "").lower()
                            pending = user_profile.get("pending_needs", [])
                            resolved = user_profile.get("resolved_needs", [])
                            remaining = []
                            for need in pending:
                                if any(word in product_category for word in need.lower().split()):
                                    resolved.append({
                                        "need": need,
                                        "product_id": product.get("product_id"),
                                        "name": product.get("name", ""),
                                    })
                                else:
                                    remaining.append(need)
                            user_profile["pending_needs"] = remaining
                            user_profile["resolved_needs"] = resolved

                            _listing_type = product.get("listing_type", "product")
                            has_price = bool(product.get("price_inr")) and _listing_type == "product"
                            cta_title = "Buy" if has_price else "Enquire Now"
                            caption = "Tap to purchase this product." if has_price else "Tap to enquire about pricing and availability."
                            bot_response.append(
                                {
                                    "type": "quickreply",
                                    "text": presenter_output.get("message", ""),
                                    "caption": caption,
                                    "options": [{"title": cta_title}],
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

                    _apply_needs_update(user_profile, output)

                    data["bot_response"] = [{"type": "text", "text": output.get("message", "")}]
                    user_profile["service_selected"] = ""
                    return data

        except Exception as e:
            logger.exception("Exception occurred in ProductAgent")
            raise e
