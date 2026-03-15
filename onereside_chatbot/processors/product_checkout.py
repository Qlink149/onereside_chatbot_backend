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
                    button_title = button_details.get("title")

                    if msgid.startswith("buy"):
                        ids = msgid.split("$")

                        prod_id = ids[1]
                        
                        user_profile["selected_product_id"] = prod_id

                        if user_profile.get("address"):
                            data["bot_response"] = [
                               {
                                    "type": "quickreply",
                                    "text": f"Do you want to continue with this address, \n{
                                        user_profile["address"]
                                    }",
                                    "caption": "Click the edit to edit the address.",
                                    "options": [{"title": "Continue"}, {"title": "Edit Address"}],
                                    "msgid": "address_confirmation",
                                } 
                            ]
                        else:
                            data["bot_response"] = [
                                {
                                    "type": "text",
                                    "text": f"Adress Flow.",
                                }
                            ]
                            user_profile["address"] = {
                                "draft": True
                            }

                    elif msgid == "address_confirmation":
                        if button_title == "Continue":
                            data["bot_response"] = [
                               {
                                    "type": "cta_url",
                                    "text": f"Pls use the link to pay",
                                    "display_text": "pay now.",
                                    "url": "https://www.google.com/",
                                } 
                            ]
                            user_profile["service_selected"] = ""
                            user_profile["selected_product_id"] = ""
                        else:
                            data["bot_response"] = [
                                {
                                    "type": "text",
                                    "text": f"Adress Flow.",
                                }
                            ]


                        # data["bot_response"] = [
                        #     {
                        #         "type": "text",
                        #         "text": f"Product Purchase flow {prod_name}.",
                        #     }
                        # ]
 
            
            return data
        
        except Exception as e:
            logger.exception(
                "Exception occurred in GeneralAgent"
            )
            raise e