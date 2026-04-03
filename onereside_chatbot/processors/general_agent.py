from onereside_chatbot.processors.abstract_processor import Processor
from onereside_chatbot.utils.logger_config import logger
from onereside_chatbot.prompt.general_agent import build_general_agent_prompt, output_schema
from onereside_chatbot.utils.get_openai_client import openai_client
import json

class GeneralAgent(Processor):
    """Search a genral Query."""

    def should_run(self, data: dict) -> bool:
        """Determine whether the processor should run based on the input data."""
        if "bot_response" in data:
            return False
        return True
    
    async def process(self, data: dict) -> dict:
        """Process the input data and return the processed data."""
        phone_number = data["phone_number"]
        user_profile = data["user_profile"]
        username = user_profile["username"]
        brand = data.get("brand")
        
        try:
            if "text" in data["messages"]:
                user_query = data["messages"]["text"]["body"]

                # prompt 
                general_prompt = build_general_agent_prompt(
                    brand=brand
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
                    {"role": "user", "content": user_query},
                ]

                # first agent call
                response = await openai_client.responses.create(
                    model="gpt-4.1-mini",
                    instructions=general_prompt,
                    input=messages,
                    text=output_schema,
                    max_output_tokens=1000,
                )

                logger.info(
                    "Initial OpenAI response",
                    extra={
                        "response": response.model_dump(), 
                        "phone_number": phone_number
                    },
                )

                if response.output[0].type != "message":
                    raise ValueError("Model did not return final message")

                output_text = response.output[0].content[0].text
                output = json.loads(output_text)

                data["bot_response"] = [
                    {
                        "type": "text",
                        "text": output["message"]
                    }
                ]
                user_profile["service_selected"] = ""


            return data
        
        except Exception as e:
            logger.exception(
                "Exception occurred in GeneralAgent"
            )
            raise e