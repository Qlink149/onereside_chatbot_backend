
import hashlib
import hmac
import json

from fastapi import APIRouter, BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

import time

from onereside_chatbot.database.collections import idac
from onereside_chatbot.database.conversation_utils import save_user_message_only
from onereside_chatbot.database.db_utils import (
    save_to_mongo,
    save_payment,
    update_order_by_payment_link_id,
)
from onereside_chatbot.utils.format_chathistory import format_user
from onereside_chatbot.utils.pubsub import PubSubManager
from onereside_chatbot.utils.env_load import razorpay_webhook_secrete
from onereside_chatbot.constants import SUPPORT_NOTIFY_NUMBERS
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
    ProductCheckoutPipeline
)
from onereside_chatbot.processors.response_manager import ResponseManager
from onereside_chatbot.utils.logger_config import logger
from onereside_chatbot.routes.systems import router as systems_router

app = FastAPI(
    title="Athams OneReside Server",
    version="0.1.0",
    redoc_url=None,
    docs_url=None,
    openapi_url=None
)


ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "https://dash.onereside.claraai.tech",
    "https://onereside-dashboard.vercel.app"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(systems_router, prefix="")


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
        payment_link_entity = rz_payload.get("payment_link", {}).get("entity", {})
        payment_link_id = payment_link_entity.get("id")

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


@app.get("/ping")
def ping():
    """Ping endpoint to check if the server is running."""
    logger.info("Ping endpoint called")
    return {"message": "OneReside Chatbot Server is up and running"}




async def process_message(request_data: dict):
    """Process the incoming message in the background."""
    phone_number = None
    response_manager = ResponseManager()

    try:
        whatsapp_event = request_data["entry"][0]["changes"][0]["value"]

        messages = whatsapp_event["messages"][0]
        phone_number = messages["from"]
        whatsapp_username = (
            request_data["entry"][0]["changes"][0]["value"]["contacts"][0][
                "profile"
            ]["name"]
            if "contacts" in request_data["entry"][0]["changes"][0]["value"]
            else ""
        )

        data = {
            "phone_number": phone_number,
            "messages": messages,
            "whatsapp_username": whatsapp_username,
        }
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
                    user_message=messages,
                    whatsapp_username=whatsapp_username,
                )
                pubsub = PubSubManager()
                await pubsub.publish(
                    phone_number,
                    {
                        "type": "user_message",
                        "phone_number": phone_number,
                        "content": format_user(user_message=messages, phone_number=phone_number),
                        "whatsapp_username": whatsapp_username,
                        "timestamp": int(time.time()),
                    },
                )
            except Exception as e:
                logger.exception(
                    "Error handling message during human takeover",
                    extra={"exception": e, "phone_number": phone_number},
                )
            logger.info("Human takeover active — bot suppressed", extra={"phone_number": phone_number})
            return

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

            save_to_mongo(data=data)
            response_manager.handle_responses(data=data)

        else:
            logger.info(
                "Going to service selected pipeline",
                extra={
                    "phone_number": phone_number,
                    "service_selected": data["user_profile"][
                        "service_selected"
                    ],
                },
            )
            user_profile = data["user_profile"]

            if user_profile["service_selected"] == ServiceList.GENERAL.value:
                # No brand scanned — route to One Reside agent instead of brand-specific general agent
                pipeline = OneResidePipeline() if not data.get("brand") else GeneralPipeline()

            elif (
                user_profile["service_selected"]
                == ServiceList.PRODUCT_SEARCH.value
            ):
                pipeline = ProductSearchPipeline()

            elif (
                user_profile["service_selected"]
                == ServiceList.ONE_RESIDE.value
            ):
                pipeline = OneResidePipeline()

            elif (
                user_profile["service_selected"]
                == ServiceList.PRODUCT_CHECKOUT.value
            ):
                pipeline = ProductCheckoutPipeline()

            data = await pipeline.run(data=data)
            save_to_mongo(data=data)
            response_manager.handle_responses(data=data)

    except Exception as e:
        logger.exception(
            "Exception occured while running message endpoint",
            extra={"exception": e, "phone_number": phone_number},
        )
        data["bot_response"] = [
            {
                "type": "text",
                "text": "Unexpected error occured.",
            }
        ]
        save_to_mongo(data=data)
        response_manager.handle_responses(data=data)


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





