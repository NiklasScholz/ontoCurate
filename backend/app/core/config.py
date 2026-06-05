from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://onto:onto@localhost:5432/onto"
    redis_url: str = "redis://localhost:6379"
    oxigraph_url: str = "http://localhost:7878"
    oxigraph_data_path: str = "/data/oxigraph"

    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # LLM Endpoints
    openai_api_key: str = ""
    openai_api_base: str = "https://chat.kiconnect.nrw/api/v1"
    default_model: str = "gpt-oss-120b"

    model_config = ConfigDict(env_file="secrets.env")


settings = Settings()
