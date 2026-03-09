
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request

from onereside_chatbot.database.db_utils import (
    save_to_mongo
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

app = FastAPI(
    title="Athams OneReside Server",
    version="0.1.0",
    redoc_url=None,
    docs_url=None,
    openapi_url=None
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(prefix="/api/v1")


@app.get("/ping")
def ping():
    """Ping endpoint to check if the server is running."""
    logger.info("Ping endpoint called")
    return {"message": "OneReside Chatbot Server is up and running"}




@app.post("/gupshup/message/onereside")
async def messages(data: Request):
    """Message endpoint to send a message to the chatbot."""
    request_data = await data.json()
    logger.info("Request received with data", extra={"data": request_data})

    try:
        if "payload" in request_data:
            logger.info("Payload found in request data, ignoring it")
            return None

        whatsapp_event = request_data["entry"][0]["changes"][0]["value"]

        # logger.info("Whatsapp event", extra={"whatsapp_event": whatsapp_event})

        if "statuses" in whatsapp_event:
            if "type" in whatsapp_event["statuses"][0]:
                status = whatsapp_event["statuses"][0]["type"]
            else:
                status = whatsapp_event["statuses"][0]["status"]
            logger.info(
                "Ignoring message with status", extra={"status": status}
            )
            return {"status": "success"}

        messages = whatsapp_event["messages"][0]
        phone_number = messages["from"]
        whatsapp_username = (
            request_data["entry"][0]["changes"][0]["value"]["contacts"][0][
                "profile"
            ]["name"]
            if "contacts" in request_data["entry"][0]["changes"][0]["value"]
            else ""
        )

        response_manager = ResponseManager()

        data = {
            "phone_number": phone_number,
            "messages": messages,
            "whatsapp_username": whatsapp_username,
        }
        logger.info(
            "Data object to pipeline",
            extra={"data": data, "phone_number": phone_number},
        )

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
                pipeline = GeneralPipeline()
                
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




