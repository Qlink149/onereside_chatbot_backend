import json
import random

from onereside_chatbot.processors.abstract_processor import Processor
from onereside_chatbot.utils.logger_config import logger
from onereside_chatbot.database.db_utils import get_product_by_id, save_order, save_enquiry
from onereside_chatbot.database.brand_utils import get_brand_by_id
from onereside_chatbot.database.order_utils import _generate_order_id
from onereside_chatbot.utils.razorpay_utils import create_payment_link
from onereside_chatbot.models.enums import FLowId
from onereside_chatbot.models.service_list import ServiceList
from onereside_chatbot.constants import SUPPORT_NOTIFY_NUMBERS, BRAND_ENQUIRY_RESPONSES, RAZORPAY_REDIRECT
from onereside_chatbot.utils.env_load import web_success_url
from onereside_chatbot.utils.trace import record_event, set_agent
from onereside_chatbot.web_channel.identity import normalise_phone
from onereside_chatbot.whatsapp_functions.template.send_product_enquiry_template import send_product_enquiry_template


def _resolve_contact_phone(user_ref: str, user_profile: dict) -> str | None:
    """Resolve a real customer phone (8–14 digits), never a ``web:<uuid>`` session key.

    Prefer checkout address phone, then identify phone (``identifiers.phone``),
    then the WhatsApp user ref when it is a real number.
    """
    candidates: list[str] = []
    personal = ((user_profile.get("address") or {}).get("personal_details") or {})
    if personal.get("phone_number"):
        candidates.append(str(personal["phone_number"]))
    identifiers = user_profile.get("identifiers") or {}
    if identifiers.get("phone"):
        candidates.append(str(identifiers["phone"]))
    if user_ref and not str(user_ref).startswith("web:"):
        candidates.append(str(user_ref))

    for raw in candidates:
        try:
            digits = normalise_phone(raw)
        except ValueError:
            continue
        if 8 <= len(digits) <= 14:
            return digits
    return None


def _razorpay_customer_contact(user_ref: str, user_profile: dict) -> str | None:
    """Alias for Razorpay ``customer.contact`` resolution."""
    return _resolve_contact_phone(user_ref, user_profile)


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
                set_agent(data, "ProductCheckoutAgent")

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
                            record_event(data, "checkout_address_submitted")

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

                    if msgid == "show_similar_oos":
                        user_profile["service_selected"] = ServiceList.PRODUCT_SEARCH.value
                        user_profile["selected_product_id"] = {}
                        data["bot_response"] = [
                            {
                                "type": "text",
                                "text": (
                                    "What are you looking for? Tell me the style, room, "
                                    "or piece and I'll find similar options."
                                ),
                            }
                        ]
                        return data

                    if msgid.startswith("enquire"):
                        brand_id = msgid.split("$")[1]
                        brand = get_brand_by_id(brand_id)

                        if brand:
                            contact_phone = _resolve_contact_phone(phone_number, user_profile)
                            record_event(data, "brand_enquiry_saved", brand_id=brand_id, brand_name=brand.get("brand_name", ""))
                            enquiry_doc = {
                                "phone_number": phone_number,
                                "username": username,
                                "type": "brand_enquiry",
                                "brand": {
                                    "brand_id": brand.get("brand_id"),
                                    "brand_name": brand.get("brand_name", ""),
                                },
                            }
                            if contact_phone:
                                enquiry_doc["contact_phone"] = contact_phone
                            save_enquiry(enquiry_doc)
                            logger.info(
                                "Brand enquiry saved",
                                extra={"phone_number": phone_number, "brand_id": brand_id},
                            )
                            notify_customer_phone = contact_phone or (
                                phone_number if not str(phone_number).startswith("web:") else ""
                            )
                            for notify_number in SUPPORT_NOTIFY_NUMBERS:
                                try:
                                    send_product_enquiry_template(
                                        phone_number=notify_number,
                                        product_name=brand.get("brand_name", ""),
                                        customer_name=username,
                                        customer_phone=notify_customer_phone,
                                    )
                                except Exception as e:
                                    logger.error(
                                        "Failed to send brand enquiry template",
                                        extra={"notify_number": notify_number, "error": e},
                                    )

                        brand_name = brand.get("brand_name", "this brand")
                        data["bot_response"] = [{"type": "text", "text": random.choice(BRAND_ENQUIRY_RESPONSES).format(brand_name=brand_name)}]
                        user_profile["service_selected"] = ""
                        return data

                    if msgid.startswith("buy"):
                        ids = msgid.split("$")
                        prod_id = ids[1]
                        product = get_product_by_id(product_id=prod_id)
                        user_profile["selected_product_id"] = product or {}

                        if button_title == "Enquire Now":
                            if product:
                                contact_phone = _resolve_contact_phone(phone_number, user_profile)
                                record_event(
                                    data, "product_enquiry_saved",
                                    product_id=prod_id, product_name=product.get("name", ""),
                                )
                                enquiry_doc = {
                                    "phone_number": phone_number,
                                    "username": username,
                                    "product": {
                                        "product_id": product.get("product_id"),
                                        "name": product.get("name"),
                                        "brand_id": product.get("brand_id"),
                                        "brand_name": product.get("brand_name", ""),
                                        "category": product.get("category"),
                                    },
                                }
                                if contact_phone:
                                    enquiry_doc["contact_phone"] = contact_phone
                                save_enquiry(enquiry_doc)
                                logger.info(
                                    "Enquiry saved",
                                    extra={"phone_number": phone_number, "product_id": prod_id},
                                )
                                notify_customer_phone = contact_phone or (
                                    phone_number if not str(phone_number).startswith("web:") else ""
                                )
                                for notify_number in SUPPORT_NOTIFY_NUMBERS:
                                    try:
                                        send_product_enquiry_template(
                                            phone_number=notify_number,
                                            product_name=product.get("name", ""),
                                            customer_name=username,
                                            customer_phone=notify_customer_phone,
                                        )
                                    except Exception as e:
                                        logger.error(
                                            "Failed to send product enquiry template",
                                            extra={"notify_number": notify_number, "error": e},
                                        )

                            product_name = product.get("name", "this item")
                            brand_name = product.get("brand_name", "")
                            brand_suffix = f" by *{brand_name}*" if brand_name else ""
                            data["bot_response"] = [
                                {
                                    "type": "text",
                                    "text": f"Your enquiry for *{product_name}*{brand_suffix} is in — the OneReside team will follow up with you shortly on pricing and next steps.\n\nFeel free to keep browsing in the meantime.",
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
                        selected_prod = user_profile.get("selected_product_id") or {}

                        if button_title == "Continue":
                            # Live stock check — block only exact out_of_stock; absent field proceeds
                            prod_id = selected_prod.get("product_id")
                            fresh = get_product_by_id(product_id=prod_id) if prod_id else None
                            if (
                                fresh
                                and str(fresh.get("inventory_status") or "").strip()
                                == "out_of_stock"
                            ):
                                record_event(
                                    data,
                                    "checkout_blocked_out_of_stock",
                                    product_id=prod_id,
                                )
                                data["bot_response"] = [
                                    {
                                        "type": "quickreply",
                                        "text": (
                                            "That piece is no longer available — "
                                            "it's just been snapped up."
                                        ),
                                        "caption": "Want me to find similar options?",
                                        "options": [{"title": "Show similar"}],
                                        "msgid": "show_similar_oos",
                                    }
                                ]
                                user_profile["service_selected"] = ""
                                user_profile["selected_product_id"] = {}
                            else:
                                amount_inr = selected_prod.get("price_inr", 0)
                                amount_paise = int(amount_inr * 100)

                                order_id = _generate_order_id()
                                callback_url = (
                                    f"{web_success_url.rstrip('/')}/order/{order_id}"
                                    if data.get("channel") == "web"
                                    else RAZORPAY_REDIRECT
                                )

                                contact_phone = _razorpay_customer_contact(
                                    phone_number, user_profile
                                )
                                if not contact_phone:
                                    logger.error(
                                        "Cannot create payment link: no valid customer phone",
                                        extra={"phone_number": phone_number},
                                    )
                                    data["bot_response"] = [
                                        {
                                            "type": "text",
                                            "text": (
                                                "I need a valid mobile number to create "
                                                "your payment link. Please share your "
                                                "10-digit phone number and try again."
                                            ),
                                        }
                                    ]
                                    return data

                                personal = (
                                    (user_profile.get("address") or {}).get(
                                        "personal_details"
                                    )
                                    or {}
                                )
                                identifiers = user_profile.get("identifiers") or {}
                                contact_name = (
                                    " ".join(
                                        p
                                        for p in (
                                            personal.get("first_name"),
                                            personal.get("last_name"),
                                        )
                                        if p
                                    ).strip()
                                    or username
                                )
                                contact_email = (
                                    personal.get("email")
                                    or identifiers.get("email")
                                    or ""
                                )

                                payment_link_response = create_payment_link(
                                    amount=amount_paise,
                                    phone=contact_phone,
                                    name=contact_name,
                                    email=contact_email,
                                    description=f"Order for {selected_prod.get('name', '')}",
                                    callback_url=callback_url,
                                )

                                record_event(
                                    data, "payment_link_created",
                                    product_id=selected_prod.get("product_id"),
                                    amount_inr=amount_inr,
                                    payment_link_id=payment_link_response.get("id"),
                                )

                                order_doc = {
                                    "order_id": order_id,
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
                                if contact_phone:
                                    order_doc["contact_phone"] = contact_phone
                                save_order(order_doc)

                                data["bot_response"] = [
                                   {
                                        "type": "cta_url",
                                        "text": f"Click below to complete your payment of ₹{amount_inr} for {selected_prod.get('name', 'your order')}.",
                                        "display_text": "Pay Now",
                                        "url": payment_link_response.get("short_url"),
                                        "order_id": order_id,
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
                        record_event(data, "checkout_cancelled")
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
                            "text": f"Please complete the checkout first., \n{user_profile['address']}",
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
