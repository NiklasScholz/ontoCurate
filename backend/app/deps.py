from uuid import UUID

from fastapi import Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.core.security import create_access_token, decode_token, set_auth_cookie
from app.models.user import User
from app.repositories.user import UserRepository
from app.repositories.workspace import WorkspaceMemberRepository


async def get_current_user(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> User:
    token = request.cookies.get("access_token")
    if not token:
        raise UnauthorizedException()
    payload = decode_token(token)
    user = await UserRepository(session).get_by_email(payload["sub"])
    if not user:
        raise UnauthorizedException()
    # re-issue cookie so only after 60min of inactivity users are logged out
    set_auth_cookie(response, create_access_token(subject=user.email))
    return user


def require_role(*roles: str):
    """Dependency that checks if current user has the required role for the respective endpoint. Raises ForbiddenException if the user does not have the required role."""

    async def check(
        workspace_id: UUID,
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> None:
        role = await WorkspaceMemberRepository(session).get_role(
            workspace_id, current_user.id
        )
        if role not in roles:
            raise ForbiddenException()

    return check
