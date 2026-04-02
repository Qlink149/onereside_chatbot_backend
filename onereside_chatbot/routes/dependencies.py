from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt, JWTError

from onereside_chatbot.utils.env_load import jwt_secret

ALGORITHM = "HS256"
_bearer = HTTPBearer(auto_error=False)


def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(_bearer)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        jwt.decode(credentials.credentials, jwt_secret, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
