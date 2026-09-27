"""Schema for structured output requested from an AI ticket analysis."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.ticket import TicketCategory, TicketPriority


class TicketAIAnalysisOutput(BaseModel):
    """Validated AI output for classifying and summarizing a ticket."""

    category: TicketCategory
    priority: TicketPriority
    summary: str = Field(min_length=1, max_length=2000)
    requires_human: bool


class TicketAnalysisPendingResponse(BaseModel):
    """Ticket exists but no AI analysis has been persisted yet."""

    ticket_id: UUID
    status: Literal["pending"] = "pending"


class TicketAnalysisCompletedResponse(BaseModel):
    """Persisted AI analysis shown to customer-support operators."""

    ticket_id: UUID
    status: Literal["completed"] = "completed"
    category: TicketCategory
    priority: TicketPriority
    summary: str
    requires_human: bool
