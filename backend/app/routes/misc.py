from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import NotFoundException
from app.deps import get_current_user
from app.models.user import User
from app.repositories.user import UserRepository

users_router = APIRouter(
    prefix="/users", tags=["users"], dependencies=[Depends(get_current_user)]
)


@users_router.get("/lookup")
async def lookup_user(
    user_info: str,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
):
    user = await UserRepository(session).get_by_email(
        user_info
    ) or await UserRepository(session).get_by_username(user_info)
    if user is None:
        raise NotFoundException(f"User with info {user_info} not found")
    return {"id": str(user.id), "email": user.email, "name": user.name or user.username}


schemas_router = APIRouter(
    prefix="/schemas", tags=["schemas"], dependencies=[Depends(get_current_user)]
)


@schemas_router.get("/")
async def get_schemas():
    config_path = Path(__file__).parent.parent.parent / "config"
    return [f.name for f in config_path.iterdir() if f.is_dir()]
