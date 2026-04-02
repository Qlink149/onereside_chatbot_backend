from fastapi import Cookie, HTTPException

from onereside_chatbot.utils.env_load import dashboard_api_key

COOKIE_NAME = "dashboard_session"


def verify_api_key(dashboard_session: str | None = Cookie(default=None, alias=COOKIE_NAME)):
    if not dashboard_api_key or dashboard_session != dashboard_api_key:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return dashboard_session
