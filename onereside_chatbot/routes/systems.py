from fastapi import APIRouter, Depends

from onereside_chatbot.routes.dependencies import verify_api_key
from onereside_chatbot.routes.system_sub_routes import brands, orders, payments, products, users
from onereside_chatbot.routes.system_sub_routes import auth
from onereside_chatbot.utils.logger_config import logger

router = APIRouter(prefix="/system", tags=["system"])
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(products.router)
router.include_router(brands.router)
router.include_router(orders.router)
router.include_router(payments.router)


@router.get("/ping")
def ping(_: str = Depends(verify_api_key)):
    """Health check endpoint for the dashboard."""
    logger.info("Dashboard ping endpoint called")
    return {"status": "ok", "message": "OneReside system is up and running"}
