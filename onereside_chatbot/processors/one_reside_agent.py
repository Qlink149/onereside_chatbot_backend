import json

from onereside_chatbot.database.brand_utils import get_brands_summary, get_brand_by_id
from onereside_chatbot.database.chroma.utils import semantic_brand_search
from onereside_chatbot.processors.abstract_processor import Processor
from onereside_chatbot.prompt.one_reside import one_reside_agent_prompt, output_schema, search_brands_tool, list_all_brands_tool
from onereside_chatbot.utils.get_openai_client import openai_client
from onereside_chatbot.utils.logger_config import logger
from onereside_chatbot.utils.trace import record_tool_call, set_agent


class OneResideAgent(Processor):
    """One Reside platform concierge — handles platform questions and brand discovery."""

    def should_run(self, data: dict) -> bool:
        if "bot_response" in data:
            return False
        return True

    def handle_search_brands(self, query: str) -> str:
        """Semantic search for brands matching the user's query."""
        brands = semantic_brand_search(query)
        # Chroma only stores name/description/categories — enrich the top match
        # with its full Mongo doc so founder/detail questions can be answered
        # from real data instead of the model guessing.
        if brands:
            top = get_brand_by_id(brands[0].get("brand_id", ""))
            if top:
                brands[0]["brand_additional_context"] = top.get("brand_additional_context", "")
                brands[0]["brand_description"] = top.get("brand_description", "")
        return json.dumps({"query": query, "brands": brands})

    def handle_list_all_brands(self) -> str:
        """Return all brand names from MongoDB."""
        brands = get_brands_summary()
        return json.dumps({"brands": brands})

    async def process(self, data: dict) -> dict:
        phone_number = data["phone_number"]
        user_profile = data["user_profile"]
        username = user_profile["username"]

        if not self.should_run(data):
            logger.info("Skipping processor", extra={"processor": self.__class__.__name__, "phone_number": phone_number})
            return data

        try:
            if "text" not in data["messages"]:
                return data

            user_query = data["messages"]["text"]["body"]

            set_agent(data, "OneResideAgent", model="gpt-4.1-mini")

            chat_history = user_profile.get("chat_history", [])[-10:]
            chat_history_str = "\n".join(
                f"{c.get('role','').capitalize()}: {c.get('content','')}"
                for c in chat_history
            )

            messages = [
                {"role": "system", "content": f"Username: {username}"},
                {"role": "system", "content": f"Recent chat history:\n{chat_history_str}"},
                {"role": "user", "content": user_query},
            ]

            # Agent loop — handles optional tool call
            response = await openai_client.responses.create(
                model="gpt-4.1-mini",
                instructions=one_reside_agent_prompt,
                input=messages,
                tools=[search_brands_tool, list_all_brands_tool],
                tool_choice="auto",
                text=output_schema,
                max_output_tokens=400,
            )

            logger.info("OneReside agent response", extra={"response": response.model_dump(), "phone_number": phone_number})

            tool_calls = [item for item in response.output if item.type == "function_call"]

            if tool_calls:
                tool_outputs = []
                for tool_call in tool_calls:
                    args = json.loads(tool_call.arguments)
                    if tool_call.name == "list_all_brands":
                        tool_result = self.handle_list_all_brands()
                    else:
                        tool_result = self.handle_search_brands(args.get("query", ""))

                    logger.info("Tool invoked", extra={"tool": tool_call.name, "arguments": args, "result": tool_result})
                    record_tool_call(data, tool=tool_call.name, arguments=args, output=tool_result)
                    tool_outputs.append({
                        "type": "function_call_output",
                        "call_id": tool_call.call_id,
                        "output": tool_result,
                    })

                follow_up_messages = messages + list(response.output) + tool_outputs

                response = await openai_client.responses.create(
                    model="gpt-4.1-mini",
                    instructions=one_reside_agent_prompt,
                    input=follow_up_messages,
                    text=output_schema,
                    max_output_tokens=1000,
                )

                logger.info("OneReside agent follow-up response", extra={"response": response.model_dump(), "phone_number": phone_number})

            output_text = response.output[0].content[0].text
            output = json.loads(output_text)

            data["bot_response"] = [{"type": "text", "text": output.get("message", "")}]
            user_profile["service_selected"] = ""
            return data

        except Exception as e:
            logger.exception("Exception occurred in OneResideAgent.")
            raise e
