import json
import random
from zoneinfo import ZoneInfo

from onereside_chatbot.models.service_list import ServiceList
from onereside_chatbot.processors.abstract_processor import Processor
from onereside_chatbot.prompt.classifier import (
    one_reside_classifier,
)
from onereside_chatbot.constants import UNSUPPORTED_TYPE_RESPONSES, AGENT_REQUEST_RESPONSES, SUPPORT_NOTIFY_NUMBERS
from onereside_chatbot.whatsapp_functions.template.send_customer_support_template import send_customer_support_template
from onereside_chatbot.utils.get_openai_responses import get_openai_responses
from onereside_chatbot.utils.logger_config import logger
from onereside_chatbot.utils.trace import record_classifier, record_event

india_tz = ZoneInfo('Asia/Kolkata')

CONTEXT = one_reside_classifier

class Classifier(Processor):
    """Classifies a query based on user intent."""

    def should_run(self, data: dict) -> bool:
        """Determine whether the processor should run based on the input data."""
        if "bot_response" in data:
            return False
        elif data.get("by_pass"):
            return False
        return True


    async def process(self, data: dict) -> dict:
        """Process the input data and return the processed data."""
        phone_number = data["phone_number"]
        user_profile = data["user_profile"]

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
            if "interactive" in data["messages"]:
                interactive = data["messages"]["interactive"]

                if interactive.get("type") == "button_reply":
                    data["button_reply"] = interactive.get("button_reply")
                    button_title = data["button_reply"]["title"]
                    if button_title == "Buy":
                        record_event(data, "classifier_shortcut", rule="button_reply", button=button_title, routed_to=ServiceList.PRODUCT_CHECKOUT.value)
                        user_profile["service_selected"] = ServiceList.PRODUCT_CHECKOUT.value
                        return data
                    if button_title == "Enquire Now":
                        record_event(data, "classifier_shortcut", rule="button_reply", button=button_title, routed_to=ServiceList.PRODUCT_CHECKOUT.value)
                        user_profile["service_selected"] = ServiceList.PRODUCT_CHECKOUT.value
                        return data

                if "nfm_reply" in interactive:
                    if interactive["nfm_reply"]["name"] == "flow":
                        record_event(data, "classifier_shortcut", rule="flow_reply", routed_to=ServiceList.PRODUCT_CHECKOUT.value)
                        user_profile["service_selected"] = ServiceList.PRODUCT_CHECKOUT.value
                        return data

            elif "text" in data["messages"]:
                user_query = data["messages"]["text"]["body"]


                if user_query.strip().lower() == "stop":
                    data["bot_response"] = [
                        {
                            "type": "text",
                            "text": "You’ve been successfully unsubscribed.",
                        }
                    ]
                    return data

                logger.info(
                    "Request received to classify query",
                    extra={"phone_number": phone_number, "query": user_query},
                )

                chat_history = data["user_profile"].get("chat_history", [])
                recent_chats = chat_history[-8:]

                # Convert chat history list of dicts to a single string
                chat_history_str = ""
                for chat in recent_chats:
                    role = chat.get("role", "")
                    content = chat.get("content", "")
                    chat_history_str += f"{role.capitalize()}: {content}\n"

                classifier_response = await get_openai_responses(
                    agent_name="Classifier Agent",
                    model="gpt-4.1-mini",
                    instruction=CONTEXT,
                    messages=[
                        {
                            "role": "system",
                            "content": f"Chat history: {chat_history_str}",
                        },
                        {
                            "role": "user",
                            "content": f"User Query: {user_query}",
                        },
                    ],
                )

                logger.info(
                    "Classifier agent response",
                    extra={
                        "respnse": classifier_response,
                        "phone_number": phone_number,
                    },
                )

                classifier_response = json.loads(classifier_response)
                category = classifier_response["category"].strip().lower()

                record_classifier(
                    data,
                    category=category,
                    raw_response=classifier_response,
                    model="gpt-4.1-mini",
                )

                logger.info(
                    "Classifier category",
                    extra={
                        "category": category,
                        "phone_number": phone_number,
                    },
                )

                if category == "general":
                    user_profile["service_selected"] = ServiceList.GENERAL.value
                    return data

                if category == "product":
                    user_profile["service_selected"] = ServiceList.PRODUCT_SEARCH.value
                    return data

                if category == "service_custom":
                    user_profile["service_selected"] = ServiceList.SERVICE_CUSTOM.value
                    return data

                if category == "one_reside":
                    user_profile["service_selected"] = ServiceList.ONE_RESIDE.value
                    return data

                if category == "agent_request":
                    record_event(data, "agent_request_raised")
                    user_profile["agent_request"] = True
                    data["bot_response"] = [
                        {
                            "type": "text",
                            "text": random.choice(AGENT_REQUEST_RESPONSES),
                        }
                    ]
                    for notify_number in SUPPORT_NOTIFY_NUMBERS:
                        try:
                            send_customer_support_template(
                                phone_number=notify_number,
                                customer_name=user_profile.get("username", phone_number),
                                customer_phone=phone_number,
                            )
                        except Exception as e:
                            logger.error(
                                "Failed to send customer support template",
                                extra={"notify_number": notify_number, "error": e},
                            )
                    return data

            else:
                record_event(data, "unsupported_message_type", msg_type=data["messages"].get("type"))
                data["bot_response"] = [
                    {
                        "type": "text",
                        "text": random.choice(UNSUPPORTED_TYPE_RESPONSES),
                    }
                ]

            return data
        except Exception as e:
            logger.exception(
                "Exception occured while running classifier.",
                extra={"exception": e, "phone_number": phone_number},
            )
            raise e
