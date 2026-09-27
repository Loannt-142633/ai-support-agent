"""Delivery state is persisted around a single email send attempt."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.models.ticket import Ticket
from app.models.ticket_suggested_answer import TicketSuggestedAnswer
from app.models.user import User
from app.services.email_sender import EmailDeliveryError
from app.services.suggested_answer_delivery_service import (
    SuggestedAnswerDeliveryFailedError,
    SuggestedAnswerDeliveryService,
)


def _setup() -> tuple[SuggestedAnswerDeliveryService, TicketSuggestedAnswer, AsyncMock, AsyncMock]:
    ticket_id = uuid4()
    draft = TicketSuggestedAnswer(
        id=uuid4(),
        ticket_id=ticket_id,
        ai_content="AI answer",
        staff_content="Staff answer",
        status="approved",
        reviewed_at=datetime.now(UTC),
    )
    ticket = Ticket(id=ticket_id, title="Refund", description="Question")
    ticket.user = User(id=uuid4(), name="Ada", email="ada@example.com")
    tickets = AsyncMock()
    tickets.get_with_user.return_value = ticket
    drafts = AsyncMock()
    drafts.get_for_ticket_for_update.return_value = draft
    sender = AsyncMock()
    session = AsyncMock()
    return SuggestedAnswerDeliveryService(tickets, drafts, sender, session), draft, sender, session


def test_pending_send_is_committed_before_smtp_and_sent_after_acceptance() -> None:
    service, draft, sender, session = _setup()
    commits: list[str] = []

    async def commit() -> None:
        commits.append(draft.status)

    async def send(**_: str) -> None:
        assert commits == ["pending_send"]
        assert draft.sent_at is None

    session.commit.side_effect = commit
    sender.send.side_effect = send

    result = asyncio.run(service.send(draft.ticket_id, draft.id))

    assert result is draft
    assert commits == ["pending_send", "sent"]
    assert draft.sent_at is not None
    sender.send.assert_awaited_once()


def test_smtp_failure_is_committed_as_send_failed() -> None:
    service, draft, sender, session = _setup()
    commits: list[str] = []

    async def commit() -> None:
        commits.append(draft.status)

    session.commit.side_effect = commit
    sender.send.side_effect = EmailDeliveryError("SMTP rejected the recipient")

    with pytest.raises(SuggestedAnswerDeliveryFailedError):
        asyncio.run(service.send(draft.ticket_id, draft.id))

    assert commits == ["pending_send", "send_failed"]
    assert draft.sent_at is None
    assert draft.send_failure_reason == "SMTP rejected the recipient"
