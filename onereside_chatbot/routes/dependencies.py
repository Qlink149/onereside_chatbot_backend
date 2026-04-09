from fastapi import HTTPException, Header
from jose import jwt, JWTError, ExpiredSignatureError

from onereside_chatbot.utils.env_load import jwt_secret

ALGORITHM = "HS256"


def verify_api_key(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.removeprefix("Bearer ")
    try:
        jwt.decode(token, jwt_secret, algorithms=[ALGORITHM])
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired")
    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
