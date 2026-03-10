from onereside_chatbot.processors.abstract_processor import Processor
from onereside_chatbot.utils.logger_config import logger
import re

from onereside_chatbot.database.db_utils import get_brand_by_id, get_brand_by_name

class QRProcessor(Processor):
    """Search a genral Query."""

    def should_run(self, data: dict) -> bool:
        """Determine whether the processor should run based on the input data."""
        if "bot_response" in data:
            return False
        return True
    
    def detect_qr_message(self, text: str) -> dict:
        """
        Checks if the message is a QR scanned prefilled message.
        """
        pattern = r"I'm interested in (.+?) featured in One Reside"
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            return {
                "is_qr": True,
                "brand_name": match.group(1).strip()
            }

        return {
            "is_qr": False,
            "brand_name": None
        }
    
    async def process(self, data: dict) -> dict:
        """Process the input data and return the processed data."""
        phone_number = data["phone_number"]
        user_profile = data.get("user_profile")

        if not self.should_run(data):
            logger.info(
                "Skipping processor",
                extra={
                    "processor": self.__class__.__name__,
                    "phone_number": phone_number,
                },
            )
            return data
        

        if "text" in data["messages"]:
            user_query = data["messages"]["text"]["body"]

            qr_check = self.detect_qr_message(text=user_query)

            if qr_check and qr_check.get("is_qr"):
                current_brand = get_brand_by_name(qr_check.get("brand_name").strip())

                if current_brand:
                    user_profile["past_brand"] = user_profile.get("current_brand", "")
                    user_profile["current_brand"] = current_brand.get("brand_id")

                    data["brand"] = current_brand

                else:
                    data["bot_response"] = [
                        {
                            "type": "text",
                            "text": "❌ Invalid QR Code Scanned!",
                        }
                    ]

            else:
                if user_profile.get("current_brand"):
                    current_brand = get_brand_by_id(brand_id=user_profile.get("current_brand"))

                    if current_brand:
                        data["brand"] = current_brand
                    else:
                        data["bot_response"] = [
                            {
                                "type": "text",
                                "text": "The Brand no longer exist try scanning new qr.",
                            }
                        ]
                    
                else:
                    pass  # no brand context — product search handles all-brands mode


        return data