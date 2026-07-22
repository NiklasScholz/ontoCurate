import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / "secrets.env")

# Seperate to dev database to avoid dropping data accidentally during testing
dev_db_url = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://onto:onto@localhost:5432/onto"
)
TEST_DB_NAME = "onto_test"
test_db_url = dev_db_url.rsplit("/", 1)[0] + f"/{TEST_DB_NAME}"
os.environ["DATABASE_URL"] = test_db_url

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.database import Base, get_session
from app.core.limiter import limiter
from app.main import app

# disable rate limiting that requires redis
limiter.enabled = False


def _admin_db_url() -> str:
    # Maintenance database from postgres
    # needed to create the test database if it doesn't exist
    return dev_db_url.rsplit("/", 1)[0] + "/postgres"


@pytest.fixture(scope="session", autouse=True)
def create_test_database():
    async def create() -> None:
        admin_engine = create_async_engine(
            _admin_db_url(), isolation_level="AUTOCOMMIT"
        )
        try:
            async with admin_engine.connect() as conn:
                exists = await conn.scalar(
                    text("SELECT 1 FROM pg_database WHERE datname = :name"),
                    {"name": TEST_DB_NAME},
                )
                if not exists:
                    await conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
        finally:
            await admin_engine.dispose()

    asyncio.run(create())


@pytest.fixture(scope="session")
async def engine():
    engine = create_async_engine(test_db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def session(engine):
    """
    Roll back after each test to avoid side effects.
    """
    async with engine.connect() as connection:
        transaction = await connection.begin()
        async_session = AsyncSession(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )

        app.dependency_overrides[get_session] = lambda: async_session
        try:
            yield async_session
        finally:
            app.dependency_overrides.pop(get_session, None)
            await transaction.rollback()


@pytest.fixture()
async def client(session):
    transport = ASGITransport(
        app=app
    )  # used to test the FastAPI app without running a server
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
