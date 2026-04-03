import json
import random
from zoneinfo import ZoneInfo

from onereside_chatbot.models.service_list import ServiceList
from onereside_chatbot.processors.abstract_processor import Processor
from onereside_chatbot.prompt.classifier import (
    one_reside_classifier,
)
from onereside_chatbot.constants import UNSUPPORTED_TYPE_RESPONSES
from onereside_chatbot.utils.get_openai_responses import get_openai_responses
from onereside_chatbot.utils.logger_config import logger

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
                    if data["button_reply"]["title"] == "Buy":
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

                if category == "one_reside":
                    user_profile["service_selected"] = ServiceList.ONE_RESIDE.value
                    return data
                
            else:
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
