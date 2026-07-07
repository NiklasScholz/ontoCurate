from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> User | None:
        result = await self.session.execute(select(User).where(User.name == name))
        return result.scalar_one_or_none()

    async def create(
        self,
        email: str,
        password_hash: str,
        name: str | None = None,
        provider: str = "local",
    ) -> User:
        user = User(
            email=email, password_hash=password_hash, name=name, provider=provider
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def get_by_provider(self, provider: str, provider_id: str) -> User | None:
        result = await self.session.execute(
            select(User).where(
                User.provider == provider, User.provider_id == provider_id
            )
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        email: str,
        name: str | None,
        picture: str | None,
        provider: str,
        provider_id: str,
    ) -> User:
        user = await self.get_by_provider(
            provider, provider_id
        ) or await self.get_by_email(email)
        if user is None:
            user = User(
                email=email,
                name=name,
                picture=picture,
                provider=provider,
                provider_id=provider_id,
            )
            self.session.add(user)
            await self.session.commit()
            await self.session.refresh(user)
        if user.picture != picture:
            user.picture = picture
            await self.session.commit()
        return user

    async def delete(self, user: User) -> None:
        await self.session.delete(user)
        await self.session.commit()
