import json
import random

from onereside_chatbot.processors.abstract_processor import Processor
from onereside_chatbot.utils.logger_config import logger
from onereside_chatbot.database.db_utils import get_product_by_id, save_order, save_enquiry
from onereside_chatbot.utils.razorpay_utils import create_payment_link
from onereside_chatbot.models.enums import FLowId
from onereside_chatbot.constants import ENQUIRY_RESPONSES

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

                if "nfm_reply" in data["messages"]["interactive"]:
                    nfm_reply = data["messages"]["interactive"]["nfm_reply"]
                    if nfm_reply["name"] == "flow":
                        flow_data = json.loads(nfm_reply["response_json"])
                        if flow_data.get("flow_token") in {FLowId.CHECKOUT_ADDRESS.value}:
                            logger.info(
                                "checkout address data received data received",
                                extra={"phone_number": phone_number},
                            )

                            address = {
                                "address": flow_data.get("screen_0_Complete_Address_0", username),
                                "pin_code": flow_data.get("screen_0_Pin_Code_1", ""),
                                "city": flow_data.get("screen_0_City_2", ""),
                                "state": flow_data.get("screen_0_State_3", ""),
                                "country": flow_data.get("screen_0_Country_4", ""),
                                "personal_details": {
                                    "first_name": flow_data.get("screen_1_First_Name_0", ""),
                                    "last_name": flow_data.get("screen_1_Last_Name_1", ""),
                                    "phone_number": flow_data.get("screen_1_Phone_Number_2", ""),
                                    "email": flow_data.get("screen_1_Email_3", ""),
                                    "wa_phone": phone_number,
                                }
                            }

                            user_profile["address"] = address

                            formatted_address = (
                                f"{address['personal_details']['first_name']} {address['personal_details']['last_name']}\n"
                                f"{address['address']}\n"
                                f"{address['city']}, {address['state']} - {address['pin_code']}\n"
                                f"{address['country']}\n"
                                f"📞 {address['personal_details']['phone_number']}"
                            )

                            data["bot_response"] = [
                                {
                                    "type": "quickreply",
                                    "text": f"Confirm this address:\n\n{formatted_address}",
                                    "caption": "You can edit if needed.",
                                    "options": [{"title": "Continue"}, {"title": "Edit Address"}],
                                    "msgid": "address_confirmation",
                                }
                            ]
                    
                
                elif "button_reply" in data:
                    button_details = data.get("button_reply")

                    payload = json.loads(button_details.get("id"))
                    msgid = payload.get("msgid")
                    button_title = button_details.get("title")

                    if msgid.startswith("buy"):
                        ids = msgid.split("$")
                        prod_id = ids[1]
                        product = get_product_by_id(product_id=prod_id)
                        user_profile["selected_product_id"] = product or {}

                        if button_title == "Enquire Now":
                            if product:
                                save_enquiry({
                                    "phone_number": phone_number,
                                    "username": username,
                                    "product": {
                                        "product_id": product.get("product_id"),
                                        "name": product.get("name"),
                                        "brand_id": product.get("brand_id"),
                                        "brand_name": product.get("brand_name", ""),
                                        "category": product.get("category"),
                                    },
                                })
                                logger.info(
                                    "Enquiry saved",
                                    extra={"phone_number": phone_number, "product_id": prod_id},
                                )
                            
                            data["bot_response"] = [
                                {
                                    "type": "text",
                                    "text": random.choice(ENQUIRY_RESPONSES),
                                }
                            ]
                            user_profile["service_selected"] = ""
                            user_profile["selected_product_id"] = {}
                            return data


                        if user_profile.get("address"):

                            address = user_profile["address"]

                            formatted_address = (
                                f"{address['personal_details']['first_name']} {address['personal_details']['last_name']}\n"
                                f"{address['address']}\n"
                                f"{address['city']}, {address['state']} - {address['pin_code']}\n"
                                f"{address['country']}\n"
                                f"📞 {address['personal_details']['phone_number']}"
                            )

                            data["bot_response"] = [
                                {
                                    "type": "quickreply",
                                    "text": f"Confirm this address:\n\n{formatted_address}",
                                    "caption": "You can edit if needed.",
                                    "options": [{"title": "Continue"}, {"title": "Edit Address"}],
                                    "msgid": "address_confirmation",
                                }
                            ]
                        else:
                            data["bot_response"] = [
                                {
                                    "type": "flow",
                                    "flow": "address"
                                }
                            ]

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
                                    "type": "flow",
                                    "flow": "address"
                                }
                            ]

                    elif msgid == "cancel_purchase":
                        user_profile["service_selected"] = ""
                        user_profile["selected_product_id"] = {}

                        data["bot_response"] = [
                            {
                                "type": "text",
                                "text": "Your checkout has been cancelled. You can continue browsing."
                            }
                        ]

                else:

                    data["bot_response"] = [
                        {
                            "type": "quickreply",
                            "text": f"Please complete the checkout first., \n{
                                 user_profile["address"]
                            }",
                            "caption": "Click the button to cancel.",
                            "options": [{"title": "cancel purchase"}],
                            "msgid": "cancel_purchase",
                        } 
                    ]
            
            return data
        
        except Exception as e:
            logger.exception(
                "Exception occurred in GeneralAgent"
            )
            raise e