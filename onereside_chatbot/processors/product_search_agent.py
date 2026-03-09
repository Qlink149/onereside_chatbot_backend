from onereside_chatbot.processors.abstract_processor import Processor
from onereside_chatbot.utils.logger_config import logger
from onereside_chatbot.prompt.product_search import (
    build_product_presenter_prompt,
    build_product_recommender_prompt,
    output_schema,
    presenter_output_schema,
    semantic_search_tool,
    keyword_search_tool
)
from onereside_chatbot.utils.get_openai_client import openai_client
from onereside_chatbot.database.collections import product as pd
from onereside_chatbot.database.chroma.utils import semantic_search
from onereside_chatbot.database.db_utils import get_product_by_id

import json


class ProductAgent(Processor):
    """Search a product search Query."""

    def should_run(self, data: dict) -> bool:
        """Determine whether the processor should run based on the input data."""
        if "bot_response" in data:
            return False
        return True

    def handle_semantic_search(self, args: dict, brand_id: str, exclude_ids: list) -> list:
        """Handle semantic search tool call. Returns list of product docs from MongoDB."""
        try:
            query = args.get("query", "")

            # Vector search → returns product IDs
            product_ids = semantic_search(
                query=query,
                brand_id=brand_id,
                exclude_ids=exclude_ids,
                n_results=3
            )

            if not product_ids:
                return []

            # Fetch full product docs from MongoDB
            products = list(pd.find(
                {"product_id": {"$in": product_ids}},
                {"_id": 0, "media_url": 0}
            ))

            logger.info(
                "Semantic search results",
                extra={"query": query, "results": [p.get("id") for p in products]}
            )

            return products

        except Exception as e:
            logger.error("Error in semantic search handler", extra={"error": e})
            return []

    def handle_keyword_search(self, args: dict, brand_id: str, exclude_ids: list) -> list:
        try:
            query = {"brand_id": brand_id}

            if args.get("category"):
                query["category"] = args["category"]

            if args.get("ideal_for"):
                query["ideal_for"] = args["ideal_for"] 

            price_min = args.get("price_min", 0)
            price_max = args.get("price_max", 0)
            if price_min > 0 or (price_max > 0 and price_max < 10000000):
                price_filter = {}
                if price_min > 0:
                    price_filter["$gte"] = price_min
                if price_max > 0:
                    price_filter["$lte"] = price_max

                query["$or"] = [
                    {"price_inr": price_filter},
                    {"price_inr": None}
                ]

            if args.get("style_tags"):
                query["style_tags"] = {"$in": args["style_tags"]}

            if args.get("materials"):
                query["materials"] = {"$regex": args["materials"], "$options": "i"}

            if args.get("colors"):
                query["colors_available"] = {"$regex": args["colors"], "$options": "i"}

            if exclude_ids:
                query["product_id"] = {"$nin": exclude_ids} 

            products = list(pd.find(query, {"_id": 0, "media_url": 0}).limit(3))

            logger.info(
                "Keyword search results",
                extra={"filters": args, "results": [p.get("product_id") for p in products]}
            )

            return products

        except Exception as e:
            logger.error("Error in keyword search handler", extra={"error": e})
            return []
    
    async def process(self, data: dict) -> dict:
        """Process the input data and return the processed data."""
        phone_number = data["phone_number"]
        user_profile = data["user_profile"]
        username = user_profile["username"]
        brand = data.get("brand")
        
        
        if not self.should_run(data):
            logger.info(
                "Skipping processor",
                extra={
                    "processor": self.__class__.__name__,
                    "phone_number": phone_number,
                },
            )
            return data
        
        try:
            if "text" in data["messages"]:
                user_query = data["messages"]["text"]["body"]
                brand_id = brand.get("brand_id", "")
                shown_ids = user_profile.get("shown_product_ids", [])
                exclude_ids = shown_ids[-5:] if shown_ids else []


                # prompt 
                product_recommender_prompt = build_product_recommender_prompt(
                    brand=brand
                )
                product_presenter_prompt = build_product_presenter_prompt(
                    brand_name=brand.get("brand_name")
                )

                # chat history
                chat_history = user_profile.get("chat_history", [])[-10:]
                chat_history_str = "\n".join(
                    f"{c.get('role','').capitalize()}: {c.get('content','')}"
                    for c in chat_history
                )

                # agent input
                messages = [
                    {"role": "system", "content": f"Username: {username}"},
                    {
                        "role": "system",
                        "content": f"Recent chat history:\n{chat_history_str}",
                    },
                    {
                        "role": "system", 
                        "content": f"Last Shown Product: {user_profile.get("last_shown_product", "")}"
                    },
                    {"role": "user", "content": user_query},
                ]


                # first agent call
                response = await openai_client.responses.create(
                    model="gpt-4.1-mini",
                    instructions=product_recommender_prompt,
                    input=messages,
                    tools=[semantic_search_tool, keyword_search_tool],
                    text=output_schema,
                    max_output_tokens=200,
                )

                logger.info(
                    "Initial OpenAI response",
                    extra={
                        "response": response.model_dump(), 
                        "phone_number": phone_number
                    },
                )


                # tool handling — find the function call in output
                tool_call = None
                text_message = None

                for item in response.output:
                    if item.type == "function_call":
                        tool_call = item
                    elif item.type == "message":
                        text_message = item

                if tool_call:
                    tool_name = tool_call.name
                    args = json.loads(tool_call.arguments)

                    logger.info(
                        "Tool invoked",
                        extra={"tool_name": tool_name, "arguments": args},
                    )

                    if tool_name == "semantic_search":
                        products = self.handle_semantic_search(args, brand_id, exclude_ids)
                    elif tool_name == "keyword_search":
                        products = self.handle_keyword_search(args, brand_id, exclude_ids)
                    else:
                        products = []

                    logger.info(
                        "Tool searched producs",
                        extra={"tool_name": tool_name, "products": json.dumps(products)},
                    )

                    # feed results to presenter agent
                    messages = [
                        {"role": "system", "content": f"Username: {username}"},
                        {
                            "role": "system",
                            "content": f"Recent chat history:\n{chat_history_str}",
                        },
                        {
                            "role": "system",
                            "content": f"fetched products are: {json.dumps(products)}"
                        },
                        {
                            "role": "system", 
                            "content": f"Last Shown Product: {user_profile.get("last_shown_product", "")}"
                        },
                        {"role": "user", "content": user_query},
                    ]


                    presenter_response = await openai_client.responses.create(
                        model="gpt-4.1-mini",
                        instructions=product_presenter_prompt,
                        input=messages,
                        text=presenter_output_schema,
                        max_output_tokens=200,
                    )

                    logger.info(
                        "Presenter response",
                        extra={"response": presenter_response.model_dump(), "phone_number": phone_number},
                    )

                    presenter_output_text = presenter_response.output[0].content[0].text
                    presenter_output = json.loads(presenter_output_text)
                    
                    bot_response = []

                    if presenter_output.get("product_id"):
                        user_profile.setdefault("shown_product_ids", []).append(presenter_output.get("product_id"))
                        product = get_product_by_id(
                            product_id=presenter_output.get("product_id")
                        )

                        if product:
                            if product.get("media_url"):
                                for urls in product.get("media_url", []):
                                    bot_response.append(
                                        {
                                            "type": "media",
                                            "media_type": urls.get("type"),
                                            "url": urls.get("url"),
                                            "caption": product.get("name"),
                                            "filename": product.get("name")
                                        }
                                    )
                            
                            user_profile["last_shown_product"] = json.dumps(product)

                            bot_response.append(
                                {
                                    "type": "quickreply",
                                    "text": presenter_output.get("message", ""),
                                    "caption": "Click the cta to buy the product.",
                                    "options": [{"title": "Buy"}],
                                    "msgid": f"buy_{presenter_output.get('product_id')}"
                                }
                            )

                    else:    
                        bot_response.append(
                            {
                                "type": "text",
                                "text": presenter_output.get("message", "")
                            }
                        )

                    data["bot_response"] = bot_response
                    data["service_selected"] = ""
                    return data



                else:
                    if not text_message or text_message.type != "message":
                        raise ValueError("Model did not return final message")

                    output_text = text_message.content[0].text
                    output = json.loads(output_text)

                    data["bot_response"] = [
                        {
                            "type": "text",
                            "text": output.get("message", "")
                        }
                    ]
                    data["service_selected"] = ""
                    return data
                

        except Exception as e:
            logger.exception(
                "Exception occurred in ProductAgent"
            )
            raise e

