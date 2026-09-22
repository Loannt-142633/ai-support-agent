"""Application workflow for analyzing support ticket content."""

from app.llm.client import LLMClient
from app.models.ticket import Ticket
from app.schemas.ticket_ai_analysis import TicketAIAnalysisOutput


class TicketAnalysisService:
    """Build a ticket analysis request and return the validated AI output."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    async def analyze(self, ticket: Ticket) -> TicketAIAnalysisOutput:
        """Analyze a ticket without persisting the result."""

        return await self._llm_client.generate_structured(
            prompt=self._build_prompt(ticket),
            response_model=TicketAIAnalysisOutput,
        )

    @staticmethod
    def _build_prompt(ticket: Ticket) -> str:
        """Build a focused prompt for ticket classification and triage."""

        return f"""Analyze the following customer support ticket.

Return only the requested structured output.

Ticket title: {ticket.title}
Ticket description: {ticket.description}
Current category: {ticket.category or "unknown"}
Current priority: {ticket.priority or "unknown"}
Current status: {ticket.status or "unknown"}

Classify the ticket category as one of: general, billing, technical.
Classify the priority as one of: low, medium, high, urgent.
Write a concise summary and decide whether human review is required."""
