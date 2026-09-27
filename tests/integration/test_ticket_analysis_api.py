"""HTTP contract for reading a ticket's latest AI analysis."""

from unittest.mock import AsyncMock
from uuid import uuid4

from app.api.dependencies import (
    get_ticket_ai_analysis_repository,
    get_ticket_repository,
)
from app.main import app
from app.models.ticket import Ticket, TicketCategory, TicketPriority
from app.models.ticket_ai_analysis import TicketAIAnalysis


def test_existing_ticket_without_analysis_returns_pending(client) -> None:
    ticket_id = uuid4()
    tickets = AsyncMock()
    tickets.get.return_value = Ticket(id=ticket_id)
    analyses = AsyncMock()
    analyses.get_by_ticket_id.return_value = None
    app.dependency_overrides[get_ticket_repository] = lambda: tickets
    app.dependency_overrides[get_ticket_ai_analysis_repository] = lambda: analyses

    response = client.get(f"/api/v1/tickets/{ticket_id}/analysis")

    assert response.status_code == 200
    assert response.json() == {"ticket_id": str(ticket_id), "status": "pending"}
    tickets.get.assert_awaited_once_with(ticket_id)
    analyses.get_by_ticket_id.assert_awaited_once_with(ticket_id)


def test_completed_analysis_returns_requested_fields(client) -> None:
    ticket_id = uuid4()
    tickets = AsyncMock()
    tickets.get.return_value = Ticket(id=ticket_id)
    analyses = AsyncMock()
    analyses.get_by_ticket_id.return_value = TicketAIAnalysis(
        ticket_id=ticket_id,
        predicted_category=TicketCategory.BILLING,
        predicted_priority=TicketPriority.HIGH,
        summary="Customer reports a duplicate charge.",
        requires_human=True,
    )
    app.dependency_overrides[get_ticket_repository] = lambda: tickets
    app.dependency_overrides[get_ticket_ai_analysis_repository] = lambda: analyses

    response = client.get(f"/api/v1/tickets/{ticket_id}/analysis")

    assert response.status_code == 200
    assert response.json() == {
        "ticket_id": str(ticket_id),
        "status": "completed",
        "category": "billing",
        "priority": "high",
        "summary": "Customer reports a duplicate charge.",
        "requires_human": True,
    }
    analyses.get_by_ticket_id.assert_awaited_once_with(ticket_id)


def test_missing_ticket_returns_404_without_looking_up_analysis(client) -> None:
    ticket_id = uuid4()
    tickets = AsyncMock()
    tickets.get.return_value = None
    analyses = AsyncMock()
    app.dependency_overrides[get_ticket_repository] = lambda: tickets
    app.dependency_overrides[get_ticket_ai_analysis_repository] = lambda: analyses

    response = client.get(f"/api/v1/tickets/{ticket_id}/analysis")

    assert response.status_code == 404
    assert response.json() == {"detail": "Ticket not found"}
    analyses.get_by_ticket_id.assert_not_awaited()
