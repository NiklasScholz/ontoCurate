from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.core.config import settings
from app.core.security import decode_token


def get_user_or_ip(request: Request) -> str:
    token = request.cookies.get("access_token")
    if token:
        try:
            payload = decode_token(token)
            subject = payload.get("sub")
            if subject:
                return f"user:{subject}"
        except Exception:
            pass
    return get_remote_address(request)


limiter = Limiter(key_func=get_user_or_ip, storage_uri=settings.redis_url)
