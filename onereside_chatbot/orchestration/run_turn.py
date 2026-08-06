"""Channel-neutral turn runner — lifted from process_message."""

import time

from onereside_chatbot.channels.registry import get_sender
from onereside_chatbot.database.collections import idac
from onereside_chatbot.database.conversation_utils import save_user_message_only
from onereside_chatbot.models.service_list import ServiceList
from onereside_chatbot.orchestration.turn import Turn
from onereside_chatbot.pipelines.inference_pipeline import (
    InitialPipeline,
    GeneralPipeline,
    ProductSearchPipeline,
    OneResidePipeline,
    ProductCheckoutPipeline,
    ServiceCustomPipeline,
)
from onereside_chatbot.processors.response_manager import ResponseManager
from onereside_chatbot.utils.format_chathistory import format_user
from onereside_chatbot.utils.logger_config import logger
from onereside_chatbot.utils.pubsub import PubSubManager
from onereside_chatbot.utils.trace import record_event


def _save_to_mongo(data: dict):
    """Call through main so callers that patch main.save_to_mongo still observe writes."""
    from onereside_chatbot.main import save_to_mongo

    return save_to_mongo(data=data)


async def _publish_turn_events(data: dict) -> None:
    """Push the just-handled turn to any dashboard streaming this conversation."""
    from onereside_chatbot.main import publish_turn_events

    await publish_turn_events(data)


async def run_turn(turn: Turn) -> list[dict]:
    """Run the full message pipeline for a channel-neutral Turn."""
    from onereside_chatbot.web_channel.identity import resolve_user

    turn.user_ref = resolve_user(turn.user_ref)
    phone_number = turn.user_ref
    response_manager = ResponseManager()
    data = {
        "phone_number": turn.user_ref,
        "messages": turn.messages,
        "whatsapp_username": turn.display_name,
        "received_at": turn.received_at,
        "channel": turn.channel,
    }

    try:
        logger.info(
            "Data object to pipeline",
            extra={"data": data, "phone_number": phone_number},
        )

        # Human takeover check — read directly from DB before any pipeline runs.
        # Wrapped in its own try/except so any failure here never triggers the
        # outer except block (which would send a bot error message to the user).
        raw_profile = idac.find_one({"phone_number": phone_number}, {"human_takeover": 1})
        if raw_profile and raw_profile.get("human_takeover", {}).get("active"):
            try:
                save_user_message_only(
                    phone_number=phone_number,
                    user_message=turn.messages,
                    whatsapp_username=turn.display_name,
                    received_at=data["received_at"],
                )
                pubsub = PubSubManager()
                await pubsub.publish(
                    phone_number,
                    {
                        "type": "user_message",
                        "phone_number": phone_number,
                        "content": format_user(
                            user_message=turn.messages, phone_number=phone_number
                        ),
                        "whatsapp_username": turn.display_name,
                        "timestamp": int(time.time()),
                    },
                )
            except Exception as e:
                logger.exception(
                    "Error handling message during human takeover",
                    extra={"exception": e, "phone_number": phone_number},
                )
            logger.info(
                "Human takeover active — bot suppressed",
                extra={"phone_number": phone_number},
            )
            return []

        pipeline = InitialPipeline()
        data = await pipeline.run(data=data)

        if "bot_response" in data:
            logger.info(
                "Bot response",
                extra={
                    "bot_response": data["bot_response"],
                    "phone_number": phone_number,
                },
            )

            _save_to_mongo(data=data)
            response_manager.handle_responses(data=data)
            get_sender(phone_number).send_status("done", "")
            await _publish_turn_events(data)

        else:
            logger.info(
                "Going to service selected pipeline",
                extra={
                    "phone_number": phone_number,
                    "service_selected": data["user_profile"]["service_selected"],
                },
            )
            user_profile = data["user_profile"]

            if user_profile["service_selected"] == ServiceList.GENERAL.value:
                # No brand scanned — route to One Reside agent instead of brand-specific general agent
                pipeline = OneResidePipeline() if not data.get("brand") else GeneralPipeline()

            elif user_profile["service_selected"] == ServiceList.PRODUCT_SEARCH.value:
                pipeline = ProductSearchPipeline()

            elif user_profile["service_selected"] == ServiceList.ONE_RESIDE.value:
                pipeline = OneResidePipeline()

            elif user_profile["service_selected"] == ServiceList.PRODUCT_CHECKOUT.value:
                pipeline = ProductCheckoutPipeline()

            elif user_profile["service_selected"] == ServiceList.SERVICE_CUSTOM.value:
                pipeline = ServiceCustomPipeline()

            data = await pipeline.run(data=data)
            _save_to_mongo(data=data)
            response_manager.handle_responses(data=data)
            get_sender(phone_number).send_status("done", "")
            await _publish_turn_events(data)

    except Exception as e:
        logger.exception(
            "Exception occured while running message endpoint",
            extra={"exception": e, "phone_number": phone_number},
        )
        record_event(data, "pipeline_error", error=f"{type(e).__name__}: {e}")
        data["bot_response"] = [
            {
                "type": "text",
                "text": "Unexpected error occured.",
            }
        ]
        _save_to_mongo(data=data)
        response_manager.handle_responses(data=data)
        get_sender(phone_number).send_status("done", "")
        await _publish_turn_events(data)

    return data.get("bot_response", [])
