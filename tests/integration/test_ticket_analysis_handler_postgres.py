"""Persist ticket AI analysis and safely handle sequential redelivery."""

import asyncio
import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.db.session import SessionLocal, engine
from app.jobs.ticket_analysis_handler import TicketAnalysisJobHandler, TicketNotFoundError
from app.llm.exceptions import LLMInvalidResponseError
from app.messaging.rabbitmq import RabbitMQTicketAnalysisConsumer
from app.models.ticket import Ticket, TicketCategory, TicketPriority
from app.models.ticket_ai_analysis import TicketAIAnalysis
from app.repositories.ticket_ai_analysis_repository import TicketAIAnalysisRepository
from app.repositories.ticket_repository import TicketRepository
from app.repositories.user_repository import UserRepository
from app.services.ticket_analysis_service import TicketAnalysisService
from sqlalchemy import func, select


@pytest.mark.integration
def test_handler_persists_analysis_once_after_redelivery() -> None:
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    asyncio.run(_run_analysis_and_redelivery(), loop_factory=loop_factory)


async def _run_analysis_and_redelivery() -> None:
    user_id = None
    ticket_id = None
    failing_ticket_id = None
    try:
        async with SessionLocal() as session:
            user = await UserRepository(session).create("Analysis Test", f"{uuid4()}@example.com")
            user_id = user.id
            ticket = await TicketRepository(session).create(
                user_id=user.id,
                title="Duplicate charge",
                description="My card was charged twice.",
                category=TicketCategory.BILLING,
                priority=TicketPriority.MEDIUM,
            )
            ticket_id = ticket.id
            await session.commit()

        class FakeLLM:
            def __init__(self) -> None:
                self.calls = 0

            async def generate_structured(self, *, prompt: str, response_model: type):
                self.calls += 1
                assert "Duplicate charge" in prompt
                return response_model(
                    category=TicketCategory.BILLING,
                    priority=TicketPriority.HIGH,
                    summary="Customer reports a duplicate charge.",
                    requires_human=True,
                )

        llm = FakeLLM()
        handler = TicketAnalysisJobHandler(
            SessionLocal, TicketAnalysisService(llm), model_name="test-model"
        )
        consumer = RabbitMQTicketAnalysisConsumer(handler)
        for _ in range(2):
            message = SimpleNamespace(
                body=json.dumps({"ticket_id": str(ticket_id)}).encode(),
                message_id=str(ticket_id),
                ack=AsyncMock(),
                reject=AsyncMock(),
            )
            await consumer.process_message(message)
            message.ack.assert_awaited_once_with()
            message.reject.assert_not_awaited()

        async with SessionLocal() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(TicketAIAnalysis)
                .where(TicketAIAnalysis.ticket_id == ticket_id)
            )
            record = await TicketAIAnalysisRepository(session).get_by_ticket_id(ticket_id)
        assert count == 1
        assert record is not None
        assert record.predicted_category is TicketCategory.BILLING
        assert record.predicted_priority is TicketPriority.HIGH
        assert record.summary == "Customer reports a duplicate charge."
        assert record.requires_human is True
        assert record.model == "test-model"
        assert record.prompt_version == "v1"
        assert record.confidence is None
        assert llm.calls == 1

        async with SessionLocal() as session:
            failing_ticket = await TicketRepository(session).create(
                user_id=user_id,
                title="Invalid AI output",
                description="Please inspect this ticket.",
                category=TicketCategory.GENERAL,
                priority=TicketPriority.LOW,
            )
            failing_ticket_id = failing_ticket.id
            await session.commit()

        class FailingLLM:
            async def generate_structured(self, *, prompt: str, response_model: type):
                raise LLMInvalidResponseError("invalid structured output")

        failing_handler = TicketAnalysisJobHandler(
            SessionLocal, TicketAnalysisService(FailingLLM()), model_name="test-model"
        )
        failing_message = SimpleNamespace(
            body=json.dumps({"ticket_id": str(failing_ticket_id)}).encode(),
            message_id=str(failing_ticket_id),
            ack=AsyncMock(),
            reject=AsyncMock(),
        )
        await RabbitMQTicketAnalysisConsumer(failing_handler).process_message(failing_message)
        failing_message.ack.assert_not_awaited()
        failing_message.reject.assert_awaited_once_with(requeue=False)
        async with SessionLocal() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(TicketAIAnalysis)
                    .where(TicketAIAnalysis.ticket_id == failing_ticket_id)
                )
                == 0
            )

        with pytest.raises(TicketNotFoundError):
            await handler.handle(uuid4())
    finally:
        if user_id is not None or ticket_id is not None or failing_ticket_id is not None:
            async with SessionLocal() as session:
                for stored_ticket_id in (ticket_id, failing_ticket_id):
                    if stored_ticket_id is None:
                        continue
                    ticket = await session.get(Ticket, stored_ticket_id)
                    if ticket is not None:
                        await session.delete(ticket)
                if user_id is not None:
                    user = await UserRepository(session).get(user_id)
                    if user is not None:
                        await session.delete(user)
                await session.commit()
        await engine.dispose()
