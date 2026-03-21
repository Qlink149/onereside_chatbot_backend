import json

from onereside_chatbot.processors.abstract_processor import Processor
from onereside_chatbot.utils.logger_config import logger
from onereside_chatbot.database.db_utils import get_product_by_id, save_order
from onereside_chatbot.utils.razorpay_utils import create_payment_link

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
                        
                        product = user_profile["selected_product_id"] = get_product_by_id(product_id=prod_id)

                        if product and not product.get("price_inr"):
                            data["bot_response"] = [
                               {
                                    "type": "text",
                                    "text": "NULL Price Flow.",
                                } 
                            ]
                            user_profile["service_selected"] = ""
                            user_profile["selected_product_id"] = {}
                            return data


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
                        selected_prod = user_profile.get("selected_product_id")

                        if button_title == "Continue":
                            amount_inr = selected_prod.get("price_inr", 0)
                            amount_paise = int(amount_inr * 100)

                            payment_link_response = create_payment_link(
                                amount=amount_paise,
                                phone=phone_number,
                                name=username,
                                description=f"Order for {selected_prod.get('name', '')}",
                            )

                            order_doc = {
                                "phone_number": phone_number,
                                "username": username,
                                "product": selected_prod,
                                "address": user_profile.get("address"),
                                "amount_inr": amount_inr,
                                "amount_paise": amount_paise,
                                "payment_link_id": payment_link_response.get("id"),
                                "payment_short_url": payment_link_response.get("short_url"),
                                "razorpay_payment_id": None,
                                "payment_status": "pending",
                            }
                            save_order(order_doc)

                            data["bot_response"] = [
                               {
                                    "type": "cta_url",
                                    "text": f"Click below to complete your payment of ₹{amount_inr} for {selected_prod.get('name', 'your order')}.",
                                    "display_text": "Pay Now",
                                    "url": payment_link_response.get("short_url"),
                                }
                            ]
                            user_profile["service_selected"] = ""
                            user_profile["selected_product_id"] = {}
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