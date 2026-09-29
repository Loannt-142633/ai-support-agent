"""Application configuration."""

from functools import lru_cache
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or `.env`."""

    app_name: str = "AI Support Agent"
    app_env: Literal["local", "production"] = "production"
    debug: bool = False
    demo_staff_auth_enabled: bool = False
    demo_staff_id: str = "local-demo-staff"
    demo_staff_ticket_ids: list[UUID] = Field(default_factory=list)
    cors_origins: list[str] = ["http://localhost:3000"]
    database_url: str = "postgresql+psycopg://app:app@localhost:5432/ai_support_agent"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_timeout: float = 30.0
    embedding_model: str = "intfloat/multilingual-e5-base"
    embedding_dimension: int = 768
    document_storage_dir: str = "uploads/documents"
    max_document_size_bytes: int = 50 * 1024 * 1024
    max_chunk_size: int = 500
    max_distance: float = 0.24
    rabbitmq_url: str = "amqp://app:app@localhost:5672/"
    rabbitmq_management_url: str = "http://localhost:15672"
    document_ingestion_queue: str = "document.ingestion"
    ticket_analysis_queue: str = "ticket.analysis"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_from_email: str = ""
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    smtp_timeout: float = 30.0

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    @model_validator(mode="after")
    def validate_demo_staff_auth(self) -> "Settings":
        """Fail startup if mock auth could be enabled outside an explicit local demo."""
        if self.demo_staff_auth_enabled:
            if self.app_env != "local":
                raise ValueError("Demo staff auth requires APP_ENV=local")
            if not self.demo_staff_id.strip():
                raise ValueError("DEMO_STAFF_ID must not be blank")
            if not self.demo_staff_ticket_ids:
                raise ValueError("DEMO_STAFF_TICKET_IDS must contain at least one ticket")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
