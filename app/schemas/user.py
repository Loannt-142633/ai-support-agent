"""User API schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    """Payload for creating a user."""

    name: str = Field(min_length=1, max_length=120)
    email: EmailStr


class UserUpdate(BaseModel):
    """Payload for partially updating a user."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    email: EmailStr | None = None


class UserResponse(BaseModel):
    """Serialized user."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: EmailStr
    created_at: datetime
    updated_at: datetime
