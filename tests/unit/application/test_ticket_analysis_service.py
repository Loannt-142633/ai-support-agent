import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

from app.models.ticket import Ticket, TicketCategory, TicketPriority
from app.schemas.ticket_ai_analysis import TicketAIAnalysisOutput
from app.services.ticket_analysis_service import TicketAnalysisService


def test_analyze_ticket_delegates_to_llm_without_persistence() -> None:
    expected = TicketAIAnalysisOutput(
        category=TicketCategory.BILLING,
        priority=TicketPriority.HIGH,
        summary="The customer was charged twice.",
        requires_human=True,
    )
    llm_client = AsyncMock()
    llm_client.generate_structured.return_value = expected
    service = TicketAnalysisService(llm_client)
    ticket = Ticket(
        id=uuid4(),
        user_id=uuid4(),
        title="Duplicate charge",
        description="My card was charged twice for the same order.",
    )

    result = asyncio.run(service.analyze(ticket))

    assert result is expected
    llm_client.generate_structured.assert_awaited_once()
    request = llm_client.generate_structured.await_args.kwargs
    assert request["response_model"] is TicketAIAnalysisOutput
    assert "Duplicate charge" in request["prompt"]
    assert "charged twice" in request["prompt"]
