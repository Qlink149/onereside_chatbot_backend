import os

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str = Security(_api_key_header)):
    dashboard_api_key = os.environ.get("DASHBOARD_API_KEY")
    if not dashboard_api_key or api_key != dashboard_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return api_key
