from fastapi import Cookie, HTTPException
from jose import jwt, JWTError

from onereside_chatbot.utils.env_load import jwt_secret

COOKIE_NAME = "dashboard_session"
ALGORITHM = "HS256"


def verify_api_key(dashboard_session: str | None = Cookie(default=None, alias=COOKIE_NAME)):
    if not dashboard_session:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        jwt.decode(dashboard_session, jwt_secret, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
