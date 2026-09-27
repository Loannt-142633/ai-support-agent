"""Ticket API schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

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


class SuggestedAnswerResponse(BaseModel):
    """A review-only draft; no customer-facing action has been performed."""

    ticket_id: UUID
    status: Literal["draft"] = "draft"
    suggested_answer: str
