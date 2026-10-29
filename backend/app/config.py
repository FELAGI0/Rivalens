"""Application settings, read from environment variables via pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Postgres connection string, e.g.
    # postgresql+psycopg://rivalens:pass@postgres:5432/rivalens
    # Required: no default — the app does not run without a real database.
    database_url: str

    # OpenAI-compatible LLM API
    ai_base_url: str
    ai_api_key: str
    ai_model: str
    ai_provider: str = "openai"

    # Scheduled competitor checks
    check_interval_hours: int = 6

    # JWT auth
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 7 * 24 * 60


settings = Settings()
