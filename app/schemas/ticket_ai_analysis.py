"""Schema for structured output requested from an AI ticket analysis."""

from pydantic import BaseModel, Field

from app.models.ticket import TicketCategory, TicketPriority


class TicketAIAnalysisOutput(BaseModel):
    """Validated AI output for classifying and summarizing a ticket."""

    category: TicketCategory
    priority: TicketPriority
    summary: str = Field(min_length=1, max_length=2000)
    requires_human: bool
