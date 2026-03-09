from onereside_chatbot.processors.abstract_processor import Processor
from onereside_chatbot.utils.logger_config import logger
from onereside_chatbot.prompt.general_agent import build_general_agent_prompt, output_schema
from onereside_chatbot.utils.get_openai_client import openai_client
import json

class ProductCheckoutAgent(Processor):
    """Search a product checkout query."""

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
        
        try:
            if "interactive" in data["messages"]:
                
                if "button_reply" in data:
                    button_details = data.get("button_reply")

                    payload = json.loads(button_details.get("id"))
                    msgid = payload.get("msgid")

                    ids = msgid.split("_")

                    if ids[0] == "buy":
                        prod_name = ids[1]

                        data["bot_response"] = [
                            {
                                "type": "text",
                                "text": f"Product Purchase flow {prod_name}.",
                            }
                        ]
 
            data["service_selected"] = ""
            return data
        
        except Exception as e:
            logger.exception(
                "Exception occurred in GeneralAgent"
            )
            raise e