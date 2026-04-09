from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Response
from jose import jwt
from pydantic import BaseModel

from onereside_chatbot.utils.env_load import username, password, jwt_secret, is_production

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_NAME = "dashboard_session"
ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 1440  # 24 hours


def _create_token() -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    return jwt.encode({"sub": "admin", "exp": expire}, jwt_secret, algorithm=ALGORITHM)


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginRequest, response: Response):
    if body.username != username or body.password != password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    response.set_cookie(
        key=COOKIE_NAME,
        value=_create_token(),
        httponly=True,
        max_age=JWT_EXPIRE_MINUTES * 60,
        path="/",
        samesite="none" if is_production else "lax",
        secure=is_production,
    )
    return {"message": "Login successful"}


@router.post("/logout")
def logout(response: Response):
    response.set_cookie(
        key=COOKIE_NAME,
        value="",
        httponly=True,
        max_age=0,
        expires=0,
        path="/",
        samesite="none" if is_production else "lax",
        secure=is_production,
    )
    return {"message": "Logged out"}
