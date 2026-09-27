"""Ticket API schemas."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.ticket import TicketCategory, TicketPriority, TicketStatus


class TicketCreate(BaseModel):
    """Payload for creating a ticket."""

    user_id: UUID
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    category: TicketCategory = TicketCategory.GENERAL
    priority: TicketPriority = TicketPriority.MEDIUM


class TicketUpdate(BaseModel):
    """Payload for partially updating a ticket."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1)
    category: TicketCategory | None = None
    priority: TicketPriority | None = None
    status: TicketStatus | None = None


class TicketResponse(BaseModel):
    """Serialized ticket."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    title: str
    description: str
    category: TicketCategory
    priority: TicketPriority
    status: TicketStatus
    created_at: datetime
    updated_at: datetime


class TicketListResponse(BaseModel):
    """Paginated tickets response."""

    items: list[TicketResponse]
    total: int
    page: int
    page_size: int


class SuggestedAnswerSourceResponse(BaseModel):
    """Identity of a retrieved chunk supplied to the answer prompt."""

    model_config = ConfigDict(from_attributes=True)

    document_id: UUID
    chunk_index: int


class SuggestedAnswerEdit(BaseModel):
    """Save a staff revision while the suggested answer remains a draft."""

    staff_content: str = Field(min_length=1)

    @field_validator("staff_content")
    @classmethod
    def normalize_staff_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("staff_content must not be blank")
        return normalized


class SuggestedAnswerReject(BaseModel):
    """Record why a staff member rejected a suggested answer."""

    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("reason must not be blank")
        return normalized


class SuggestedAnswerResponse(BaseModel):
    """A persisted, unsent suggestion and its staff review state."""

    model_config = ConfigDict(from_attributes=True)

    draft_id: UUID = Field(validation_alias="id")
    ticket_id: UUID
    status: Literal["draft", "approved", "rejected", "pending_send", "sent", "send_failed"]
    suggested_answer: str = Field(validation_alias="ai_content")
    staff_content: str | None
    created_at: datetime
    updated_at: datetime | None
    reviewed_at: datetime | None
    rejection_reason: str | None
    recipient_email: str | None
    send_started_at: datetime | None
    sent_at: datetime | None
    send_failure_reason: str | None
    sources: list[SuggestedAnswerSourceResponse]

    @field_validator("created_at", "updated_at", "reviewed_at", "send_started_at", "sent_at")
    @classmethod
    def assume_utc_for_naive_database_timestamp(cls, value: datetime | None) -> datetime | None:
        """SQLite test storage loses timezone information; timestamps are written as UTC."""

        return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value
