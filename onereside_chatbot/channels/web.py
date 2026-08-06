"""Web channel sender — publishes typed events to PubSubManager."""

from onereside_chatbot.utils.pubsub import PubSubManager


class WebSender:
    """Publishes bot response parts as PubSub events keyed by user_ref."""

    def __init__(self, user_ref: str):
        self.user_ref = user_ref

    def _publish(self, event: dict) -> dict:
        pubsub = PubSubManager()
        subscribers = pubsub._subscribers.get(self.user_ref, [])
        for queue in subscribers:
            queue.put_nowait(event)
        return {"status": "submitted"}

    def send_text(self, phone_number: str, bot_response: dict):
        return self._publish({"type": "text", **bot_response})

    def send_media(self, phone_number: str, bot_response: dict):
        return self._publish({"type": "media", **bot_response})

    def send_flow(self, phone_number: str, bot_response: dict):
        return self._publish({"type": "flow", **bot_response})

    def send_list(self, phone_number: str, bot_response: dict):
        return self._publish({"type": "list", **bot_response})

    def send_quickreply(self, phone_number, bot_response):
        return self._publish({"type": "quickreply", **bot_response})

    def send_skip(self, phone_number, bot_response):
        return {"status": "submitted"}

    def send_cta_url(self, phone_number, bot_response):
        return self._publish({"type": "cta_url", **bot_response})

    def send_template(self, phone_number, bot_response: dict):
        return self._publish({"type": "template", **bot_response})

    def send_status(self, stage: str, detail: str) -> None:
        self._publish({"type": "status", "stage": stage, "detail": detail})
