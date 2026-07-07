from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import UnauthorizedException
from app.core.security import decode_token
from app.models.user import User
from app.repositories.user import UserRepository


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    token = request.cookies.get("access_token")
    if not token:
        raise UnauthorizedException()
    payload = decode_token(token)
    user = await UserRepository(session).get_by_email(payload["sub"])
    if not user:
        raise UnauthorizedException()
    return user
