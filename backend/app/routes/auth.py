import asyncio

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session
from app.core.exceptions import BadRequestException, UnauthorizedException
from app.core.limiter import limiter
from app.core.security import (
    create_access_token,
    get_password_hash,
    set_auth_cookie,
    verify_password,
)
from app.deps import get_current_user
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.user import LoginRequest, RegisterRequest, UserResponse
from app.store.writer import anonymize_curator

router = APIRouter(prefix="/auth", tags=["auth"])


class GoogleTokenRequest(BaseModel):
    credential: str


@router.post("/google", response_model=UserResponse)
async def google_auth(
    body: GoogleTokenRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    try:
        user_info = id_token.verify_oauth2_token(
            body.credential, google_requests.Request(), settings.google_client_id
        )
    except Exception as e:
        raise UnauthorizedException("Invalid Google token")
    try:
        user = await UserRepository(session).upsert(
            email=user_info["email"],
            name=user_info.get("name"),
            picture=user_info.get("picture"),
            provider="google",
            provider_id=user_info["sub"],
        )
        set_auth_cookie(response, create_access_token(subject=user.email))
    except Exception as e:
        raise BadRequestException("Failed to add user")
    return user


@router.post("/login", response_model=UserResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    user = await UserRepository(session).get_by_email(
        body.login_name
    ) or await UserRepository(session).get_by_username(body.login_name)
    if not user or user.provider != "local":
        raise UnauthorizedException("Invalid email or password")

    valid, new_hash = verify_password(body.password, user.password_hash)
    if not valid:
        raise UnauthorizedException("Invalid email or password")

    if new_hash:
        user.password_hash = new_hash
        await session.commit()

    set_auth_cookie(response, create_access_token(subject=user.email))
    return user


@router.post("/register", response_model=UserResponse)
@limiter.limit("3/hour")
async def register(
    request: Request,
    body: RegisterRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    if await UserRepository(session).get_by_email(body.email):
        raise BadRequestException("User with this email already exists")
    if body.username and await UserRepository(session).get_by_username(body.username):
        raise BadRequestException("User with this username already exists")
    user = await UserRepository(session).create(
        email=body.email,
        username=body.username,
        password_hash=get_password_hash(body.password),
        provider="local",
    )
    set_auth_cookie(response, create_access_token(subject=user.email))
    return user


@router.post("/logout")
async def logout():
    response = JSONResponse(content={"message": "logged out"})
    response.delete_cookie("access_token")
    return response


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)


@router.delete("/me")
async def delete_me(
    response: Response,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await asyncio.to_thread(anonymize_curator, current_user.id)
    await UserRepository(session).delete(current_user)
    response.delete_cookie("access_token")
    return {"message": "Account deleted"}
