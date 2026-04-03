import asyncio

from onereside_chatbot.utils.logger_config import logger


class PubSubManager:
    """Singleton async pub/sub manager using asyncio.Queue per phone number."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._subscribers: dict[str, list[asyncio.Queue]] = {}
        return cls._instance

    def subscribe(self, phone_number: str) -> asyncio.Queue:
        """Subscribe to events for a phone number. Returns a queue."""
        queue: asyncio.Queue = asyncio.Queue()
        if phone_number not in self._subscribers:
            self._subscribers[phone_number] = []
        self._subscribers[phone_number].append(queue)
        logger.info("SSE subscriber added", extra={"phone_number": phone_number})
        return queue

    def unsubscribe(self, phone_number: str, queue: asyncio.Queue) -> None:
        """Remove a subscriber queue for a phone number."""
        if phone_number in self._subscribers:
            try:
                self._subscribers[phone_number].remove(queue)
            except ValueError:
                pass
            if not self._subscribers[phone_number]:
                del self._subscribers[phone_number]
        logger.info("SSE subscriber removed", extra={"phone_number": phone_number})

    async def publish(self, phone_number: str, event: dict) -> None:
        """Publish an event to all subscribers of a phone number."""
        subscribers = self._subscribers.get(phone_number, [])
        for queue in subscribers:
            await queue.put(event)
        logger.info(
            "SSE event published",
            extra={"phone_number": phone_number, "event_type": event.get("type"), "subscriber_count": len(subscribers)},
        )
