import json

from onereside_chatbot.database.brand_utils import get_brand_by_id
from onereside_chatbot.database.chroma.utils import semantic_brand_search
from onereside_chatbot.processors.abstract_processor import Processor
from onereside_chatbot.prompt.service_custom_agent import (
    build_service_custom_agent_prompt,
    output_schema,
    search_all_brands_tool,
    search_service_brands_tool,
    search_custom_brands_tool,
)
from onereside_chatbot.utils.get_openai_client import openai_client
from onereside_chatbot.utils.logger_config import logger
from onereside_chatbot.utils.trace import record_event, record_tool_call, set_agent

TOOLS = [search_all_brands_tool, search_service_brands_tool, search_custom_brands_tool]


def _format_brand(brand: dict) -> dict:
    """Flatten a Chroma brand result into a clean summary for the LLM."""
    offers = []
    if brand.get("has_ready_products"):
        offers.append("ready products")
    if brand.get("has_custom_products"):
        offers.append("custom/made-to-order products")
    if brand.get("has_services"):
        offers.append("services")
    return {
        "brand_id": brand.get("brand_id"),
        "brand_name": brand.get("brand_name"),
        "description": brand.get("search_text", ""),
        "categories_offered": brand.get("categories_offered", ""),
        "offers": offers,
    }


def handle_search_all_brands(query: str) -> str:
    """Semantic search across all brands with no metadata filter."""
    brands = semantic_brand_search(query=query, n_results=10)
    logger.info("search_all_brands invoked", extra={"query": query, "results": len(brands)})
    return json.dumps({"query": query, "brands": [_format_brand(b) for b in brands]})


def handle_search_service_brands(query: str) -> str:
    """Semantic search filtered to brands that offer services."""
    brands = semantic_brand_search(
        query=query,
        n_results=10,
        where={"has_services": {"$eq": True}},
    )
    logger.info("search_service_brands invoked", extra={"query": query, "results": len(brands)})
    return json.dumps({"query": query, "brands": [_format_brand(b) for b in brands]})


def handle_search_custom_brands(query: str) -> str:
    """Semantic search filtered to brands that offer custom/made-to-order products."""
    brands = semantic_brand_search(
        query=query,
        n_results=10,
        where={"has_custom_products": {"$eq": True}},
    )
    logger.info("search_custom_brands invoked", extra={"query": query, "results": len(brands)})
    return json.dumps({"query": query, "brands": [_format_brand(b) for b in brands]})


_TOOL_HANDLERS = {
    "search_all_brands": handle_search_all_brands,
    "search_service_brands": handle_search_service_brands,
    "search_custom_brands": handle_search_custom_brands,
}


class ServiceCustomAgent(Processor):
    """Handles service and custom product enquiries. Can answer or present a brand with an Enquire Now button."""

    def should_run(self, data: dict) -> bool:
        if "bot_response" in data:
            return False
        return True

    async def process(self, data: dict) -> dict:
        phone_number = data["phone_number"]
        user_profile = data["user_profile"]
        username = user_profile["username"]
        brand = data.get("brand")

        try:
            if "text" not in data["messages"]:
                return data

            user_query = data["messages"]["text"]["body"]

            set_agent(data, "ServiceCustomAgent", model="gpt-5.2")

            prompt = build_service_custom_agent_prompt(brand=brand or {})

            chat_history = user_profile.get("chat_history", [])[-10:]

            shown_brands = user_profile.get("shown_brands", [])
            shown_brands_str = (
                ", ".join(f"{b['brand_name']} (brand_id: {b['brand_id']})" for b in shown_brands)
                if shown_brands else "None"
            )

            messages = [
                {"role": "system", "content": f"Username: {username}"},
                {"role": "system", "content": f"Brands already shown to this customer: {shown_brands_str}. Do not suggest the same brand again unless the customer explicitly asks for it."},
            ]

            for c in chat_history:
                role = c.get("role", "")
                if role in ("user", "assistant"):
                    messages.append({"role": role, "content": c.get("content", "")})

            messages.append({"role": "user", "content": user_query})

            response = await openai_client.responses.create(
                model="gpt-5.2",
                instructions=prompt,
                input=messages,
                tools=TOOLS,
                tool_choice="auto",
                text=output_schema,
                max_output_tokens=3000,
                reasoning={"effort": "low"},
            )

            logger.info(
                "ServiceCustomAgent initial response",
                extra={"response": response.model_dump(), "phone_number": phone_number},
            )

            tool_call = None
            text_message = None
            for item in response.output:
                if item.type == "function_call":
                    tool_call = item
                elif item.type == "message":
                    text_message = item

            # tool call takes priority — discard any text generated alongside it
            if tool_call:
                text_message = None
                args = json.loads(tool_call.arguments)
                query = args.get("query", "")

                handler = _TOOL_HANDLERS.get(tool_call.name)
                tool_result = handler(query) if handler else json.dumps({"brands": []})
                record_tool_call(data, tool=tool_call.name, arguments=args, output=tool_result)

                follow_up_messages = messages + list(response.output) + [
                    {
                        "type": "function_call_output",
                        "call_id": tool_call.call_id,
                        "output": tool_result,
                    }
                ]

                response = await openai_client.responses.create(
                    model="gpt-5.2",
                    instructions=prompt,
                    input=follow_up_messages,
                    text=output_schema,
                    max_output_tokens=3000,
                    reasoning={"effort": "low"},
                )

                logger.info(
                    "ServiceCustomAgent follow-up response",
                    extra={"response": response.model_dump(), "phone_number": phone_number},
                )

                text_message = next(
                    (item for item in response.output if item.type == "message"),
                    None,
                )

            if not text_message:
                logger.warning("ServiceCustomAgent produced no message — only reasoning or empty output", extra={"phone_number": phone_number})
                data["bot_response"] = [{"type": "text", "text": "Give me a moment, let me look into that for you."}]
                user_profile["service_selected"] = ""
                return data

            output_text = text_message.content[0].text
            output = json.loads(output_text)

            message = output["message"]
            brand_id = output.get("brand_id")
            send_brochure = output.get("send_brochure", False)

            bot_response = []

            if brand_id:
                brand_doc = get_brand_by_id(brand_id)
                if brand_doc:
                    already_shown = any(b["brand_id"] == brand_id for b in shown_brands)

                    if not already_shown or send_brochure:
                        catalogue_url = brand_doc.get("catalogue_url")
                        if catalogue_url:
                            ext = catalogue_url.rsplit(".", 1)[-1].lower() if "." in catalogue_url else ""
                            media_type = "document" if ext == "pdf" else "image"
                            bot_response.append({
                                "type": "media",
                                "media_type": media_type,
                                "url": catalogue_url,
                                "caption": brand_doc.get("brand_name", ""),
                                "filename": brand_doc.get("brand_name", "Catalogue"),
                            })

                    if not already_shown:
                        user_profile.setdefault("shown_brands", []).append({
                            "brand_id": brand_id,
                            "brand_name": brand_doc.get("brand_name", ""),
                        })

                    bot_response.append({
                        "type": "quickreply",
                        "text": message,
                        "caption": "Tap to enquire about this brand.",
                        "options": [{"title": "Enquire Now"}],
                        "msgid": f"enquire${brand_id}",
                    })

                    # Clear scanned brand if a different brand is being presented
                    scanned_brand_id = brand.get("brand_id", "") if brand else ""
                    if scanned_brand_id and brand_id != scanned_brand_id:
                        user_profile["past_brand"] = scanned_brand_id
                        user_profile["current_brand"] = ""

                    record_event(
                        data,
                        "brand_presented",
                        brand_id=brand_id,
                        brand_name=brand_doc.get("brand_name", ""),
                        already_shown=already_shown,
                        send_brochure=send_brochure,
                    )
                    logger.info(
                        "ServiceCustomAgent presenting brand",
                        extra={"brand_id": brand_id, "already_shown": already_shown, "phone_number": phone_number},
                    )
                else:
                    bot_response.append({"type": "text", "text": message})
            else:
                bot_response.append({"type": "text", "text": message})

            data["bot_response"] = bot_response
            user_profile["service_selected"] = ""

            return data

        except Exception as e:
            logger.exception("Exception occurred in ServiceCustomAgent")
            raise e
