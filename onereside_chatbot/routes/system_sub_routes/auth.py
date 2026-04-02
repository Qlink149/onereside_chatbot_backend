from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from onereside_chatbot.utils.env_load import username, password, dashboard_api_key

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_NAME = "dashboard_session"
COOKIE_MAX_AGE = 60 * 60 * 8  # 8 hours


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginRequest, response: Response):
    if body.username != username or body.password != password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    response.set_cookie(
        key=COOKIE_NAME,
        value=dashboard_api_key,
        httponly=True,
        max_age=COOKIE_MAX_AGE,
        samesite="lax",
    )
    return {"message": "Login successful"}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key=COOKIE_NAME)
    return {"message": "Logged out"}
