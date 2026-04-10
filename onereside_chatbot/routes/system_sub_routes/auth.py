from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException
from jose import jwt
from pydantic import BaseModel

from onereside_chatbot.utils.env_load import username, password, jwt_secret

router = APIRouter(prefix="/auth", tags=["auth"])

ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 1440  # 24 hours


def _create_token() -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    return jwt.encode({"sub": "admin", "exp": expire}, jwt_secret, algorithm=ALGORITHM)


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginRequest):
    if body.username != username or body.password != password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return {"token": _create_token()}


@router.post("/logout")
def logout():
    return {"message": "Logged out"}
