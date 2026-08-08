from typing import Literal

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    environment: Literal["development", "production"] = "development"
    database_url: str = "postgresql+asyncpg://onto:onto@localhost:5432/onto"
    redis_url: str = "redis://localhost:6379"
    oxigraph_url: str = "http://localhost:7878"
    oxigraph_data_path: str = "/data/oxigraph"
    google_client_id: str = ""
    google_client_secret: str = ""
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 60
    # LLM / Embedding Endpoints
    openai_api_key: str = ""
    openai_api_base: str = "https://chat.kiconnect.nrw/api/v1"
    default_model: str = "gpt-oss-120b"
    embedding_model: str = "qwen3-embedding-8b"
    max_text_length: int | None = None
    max_output_tokens: int | None = None
    wikimedia_user_agent: str = ""
    cors_allow_origins: list[str] = [
        "http://localhost:5173",
        "https://ontocurate.app",
        "https://www.ontocurate.app",
    ]

    model_config = ConfigDict(env_file="secrets.env")


settings = Settings()
