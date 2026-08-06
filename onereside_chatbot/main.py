
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pymongo.errors import DuplicateKeyError

from onereside_chatbot.database.collections import idac, orders, webhook_idempotency
from onereside_chatbot.database.conversation_utils import save_user_message_only
from onereside_chatbot.database.db_utils import (
    save_to_mongo,
    save_payment,
    update_order_by_payment_link_id,
)
from onereside_chatbot.utils.format_chathistory import format_assistant, format_user
from onereside_chatbot.utils.pubsub import PubSubManager
from onereside_chatbot.utils.env_load import razorpay_webhook_secrete, web_allowed_origins
from onereside_chatbot.constants import SUPPORT_NOTIFY_NUMBERS
from onereside_chatbot.whatsapp_functions.mark_message_read import mark_message_read
from onereside_chatbot.whatsapp_functions.template.send_user_order_payment_failed import (
    send_user_order_payment_failed,
)
from onereside_chatbot.whatsapp_functions.template.send_user_order_payment_received import (
    send_user_order_payment_received,
)
from onereside_chatbot.whatsapp_functions.template.send_admin_order_payment_received import (
    send_admin_order_payment_received,
)
from onereside_chatbot.models.service_list import ServiceList
from onereside_chatbot.pipelines.inference_pipeline import (
    InitialPipeline,
    GeneralPipeline,
    ProductSearchPipeline,
    OneResidePipeline,
    ProductCheckoutPipeline,
    ServiceCustomPipeline,
)
from onereside_chatbot.processors.response_manager import ResponseManager
from onereside_chatbot.utils.logger_config import logger
from onereside_chatbot.utils.trace import record_event
from onereside_chatbot.routes.systems import router as systems_router
from onereside_chatbot.web_channel.routes import router as web_router
from onereside_chatbot.channels.registry import get_sender
from onereside_chatbot.orchestration.turn import Turn
from onereside_chatbot.orchestration.run_turn import run_turn

app = FastAPI(
    title="Athams OneReside Server",
    version="0.1.0",
    redoc_url=None,
    docs_url=None,
    openapi_url=None
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=web_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def web_security_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/web"):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
    return response


app.include_router(systems_router, prefix="")
app.include_router(web_router, tags=["web"])


@app.post("/razorpay/webhook")
async def razorpay_webhook(request: Request):
    """Razorpay webhook endpoint to capture payment events."""
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    # Verify webhook signature
    expected_signature = hmac.new(
        razorpay_webhook_secrete.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, signature):
        logger.warning("Razorpay webhook signature mismatch")
        raise HTTPException(status_code=400, detail="Invalid signature")

    payload = json.loads(body)
    event = payload.get("event", "")
    logger.info("Razorpay webhook received", extra={"event": event, "payload": payload})

    rz_payload = payload.get("payload", {})

    PAYMENT_LINK_EVENTS = {"payment_link.paid", "payment_link.cancelled", "payment_link.expired", "payment.failed"}

    if event in PAYMENT_LINK_EVENTS:
        payment_link_entity = rz_payload.get("payment_link", {}).get("entity") or {}
        # payment.failed often omits payment_link — ack 200 so Razorpay does not retry forever
        if event == "payment.failed" and not payment_link_entity.get("id"):
            logger.info(
                "payment.failed without payment_link entity — ack only",
                extra={"event": event},
            )
            return {"status": "ok"}

        payment_link_id = payment_link_entity.get("id")
        payment_id = rz_payload.get("payment", {}).get("entity", {}).get("id") or ""
        idem_key = f"{payment_link_id}:{event}:{payment_id}"
        # Skip duplicates; reclaim key if a pending order still needs this event (re-seeded fixtures).
        if webhook_idempotency.find_one({"_id": idem_key}):
            if not orders.find_one({"payment_link_id": payment_link_id, "payment_status": "pending"}):
                return {"status": "ok"}
            webhook_idempotency.delete_one({"_id": idem_key})
        try:
            webhook_idempotency.insert_one(
                {"_id": idem_key, "created_at": datetime.now(timezone.utc)}
            )
        except DuplicateKeyError:
            return {"status": "ok"}

        # Base update — applies to all payment link events
        order_update = {
            "payment_event": event,
            "payment_status": payment_link_entity.get("status"),
        }

        if event == "payment_link.paid":
            payment_entity = rz_payload.get("payment", {}).get("entity", {})
            payment_id = payment_entity.get("id")
            save_payment({
                "payment_id": payment_id,
                "payment_link_id": payment_link_id,
                "event": event,
                "amount": payment_entity.get("amount"),
                "currency": payment_entity.get("currency"),
                "status": payment_entity.get("status"),
                "method": payment_entity.get("method"),
                "email": payment_entity.get("email"),
                "contact": payment_entity.get("contact"),
                "captured": payment_entity.get("captured"),
                "raw_payload": payload,
            })
            order_update.update({
                "razorpay_payment_id": payment_id,
                "payment_method": payment_entity.get("method"),
            })

        if payment_link_id:
            updated_order = update_order_by_payment_link_id(
                payment_link_id=payment_link_id,
                update_data=order_update,
            )

            if updated_order:
                user_phone = updated_order.get("phone_number", "")
                product_name = updated_order.get("product", {}).get("name", "your product")
                amount_inr = updated_order.get("amount_inr", 0)
                amount = f"Rs. {int(float(amount_inr)):,}"
                customer_name = updated_order.get("username", "")
                order_id = updated_order.get("order_id", payment_link_id)

                try:
                    if event == "payment_link.paid":
                        send_user_order_payment_received(
                            phone_number=user_phone,
                            amount=amount,
                            product_name=product_name,
                            order_id=order_id,
                        )
                        for admin in SUPPORT_NOTIFY_NUMBERS:
                            send_admin_order_payment_received(
                                admin_phone=admin,
                                order_id=order_id,
                                customer_name=customer_name,
                                customer_phone=user_phone,
                            )
                    else:
                        send_user_order_payment_failed(
                            phone_number=user_phone,
                            amount=amount,
                            product_name=product_name,
                            order_id=order_id,
                        )
                except Exception as notify_err:
                    logger.error(
                        "Failed to send payment WhatsApp notification",
                        extra={"error": notify_err, "event": event, "payment_link_id": payment_link_id},
                    )

    return {"status": "ok"}


@app.api_route("/ping", methods=["GET", "HEAD"])
def ping():
    """Ping endpoint to check if the server is running (GET and HEAD)."""
    return {"message": "OneReside Chatbot Server is up and running"}


async def publish_turn_events(data: dict) -> None:
    """Push the just-handled turn to any dashboard streaming this conversation.

    Emits a `user_message` event for the incoming message and a `bot_message`
    event per response part, carrying the debug trace as `context`. Failures
    are logged and swallowed — SSE is best-effort and must never break the flow.
    """
    phone_number = data.get("phone_number")
    if not phone_number:
        return
    try:
        pubsub = PubSubManager()
        now = int(time.time())

        user_message = data.get("messages")
        if user_message:
            try:
                content = format_user(user_message=user_message, phone_number=phone_number)
            except Exception:
                content = ""
            await pubsub.publish(
                phone_number,
                {
                    "type": "user_message",
                    "phone_number": phone_number,
                    "content": content,
                    "whatsapp_username": data.get("whatsapp_username", ""),
                    "timestamp": data.get("received_at") or now,
                },
            )

        # Trace values are Mongo-safe but not always JSON-safe — round-trip with
        # default=str so the SSE generator's json.dumps can never blow up on it.
        context = data.get("trace")
        if context is not None:
            context = json.loads(json.dumps(context, default=str))

        for part in data.get("bot_response", []):
            if part.get("type") == "skip":
                continue
            try:
                content = format_assistant(assistant_message=[part], phone_number=phone_number)
            except Exception:
                content = ""
            await pubsub.publish(
                phone_number,
                {
                    "type": "bot_message",
                    "phone_number": phone_number,
                    "content": content,
                    "message_type": part.get("type"),
                    "context": context,
                    "timestamp": now,
                },
            )
    except Exception as e:
        logger.exception(
            "Failed to publish turn events",
            extra={"exception": e, "phone_number": phone_number},
        )


async def process_message(request_data: dict):
    """Process the incoming message in the background."""
    whatsapp_event = request_data["entry"][0]["changes"][0]["value"]

    messages = whatsapp_event["messages"][0]
    phone_number = messages["from"]

    if "id" in messages:
        mark_message_read(messages["id"])

    whatsapp_username = (
        request_data["entry"][0]["changes"][0]["value"]["contacts"][0][
            "profile"
        ]["name"]
        if "contacts" in request_data["entry"][0]["changes"][0]["value"]
        else ""
    )

    turn = Turn(
        channel="whatsapp",
        user_ref=phone_number,
        session_id=None,
        messages=messages,
        display_name=whatsapp_username,
        received_at=int(time.time()),
    )
    await run_turn(turn)


@app.post("/gupshup/message/onereside")
async def messages(data: Request, background_tasks: BackgroundTasks):
    """Message endpoint to send a message to the chatbot."""
    request_data = await data.json()
    logger.info("Request received with data", extra={"data": request_data})

    if "payload" in request_data:
        logger.info("Payload found in request data, ignoring it")
        return JSONResponse(content={"success": True}, status_code=200)

    whatsapp_event = request_data["entry"][0]["changes"][0]["value"]

    if "statuses" in whatsapp_event:
        if "type" in whatsapp_event["statuses"][0]:
            status = whatsapp_event["statuses"][0]["type"]
        else:
            status = whatsapp_event["statuses"][0]["status"]
        logger.info(
            "Ignoring message with status", extra={"status": status}
        )
        return JSONResponse(content={"success": True}, status_code=200)

    background_tasks.add_task(process_message, request_data)
    return JSONResponse(content={"success": True}, status_code=200)





