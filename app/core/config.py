"""Application configuration."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or `.env`."""

    app_name: str = "AI Support Agent"
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:3000"]
    database_url: str = "postgresql+psycopg://app:app@localhost:5432/ai_support_agent"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"
    gemini_timeout: float = 30.0
    embedding_model: str = "intfloat/multilingual-e5-base"
    embedding_dimension: int = 768
    document_storage_dir: str = "uploads/documents"
    max_document_size_bytes: int = 50 * 1024 * 1024
    max_chunk_size: int = 500
    chunk_similarity_threshold: float = 0.85
    chunk_embedding_prefix: str = "query: "

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
