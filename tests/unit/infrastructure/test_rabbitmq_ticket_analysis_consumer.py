"""Message settlement rules for ticket analysis deliveries."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from app.jobs.ticket_analysis_handler import TicketNotFoundError
from app.llm.exceptions import LLMInvalidResponseError, LLMTimeoutError
from app.messaging.rabbitmq import RabbitMQTicketAnalysisConsumer
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError


def make_message(body: bytes) -> SimpleNamespace:
    return SimpleNamespace(body=body, message_id="delivery-1", ack=AsyncMock(), reject=AsyncMock())


def test_success_acks_once() -> None:
    ticket_id = uuid4()
    handler = SimpleNamespace(handle=AsyncMock())
    message = make_message(json.dumps({"ticket_id": str(ticket_id)}).encode())

    asyncio.run(RabbitMQTicketAnalysisConsumer(handler).process_message(message))

    handler.handle.assert_awaited_once_with(ticket_id)
    message.ack.assert_awaited_once_with()
    message.reject.assert_not_awaited()


@pytest.mark.parametrize(
    "body",
    [b"not json", b"[]", b"{}", b'{"ticket_id":123}', b'{"ticket_id":"bad"}'],
)
def test_invalid_payload_rejects_without_calling_handler(body: bytes) -> None:
    handler = SimpleNamespace(handle=AsyncMock())
    message = make_message(body)

    asyncio.run(RabbitMQTicketAnalysisConsumer(handler).process_message(message))

    handler.handle.assert_not_awaited()
    message.ack.assert_not_awaited()
    message.reject.assert_awaited_once_with(requeue=False)


@pytest.mark.parametrize("error_kind", ["missing", "invalid_response"])
def test_permanent_failure_rejects_without_retry(error_kind: str) -> None:
    ticket_id = uuid4()
    error = (
        TicketNotFoundError(ticket_id)
        if error_kind == "missing"
        else LLMInvalidResponseError("bad structured output")
    )
    handler = SimpleNamespace(handle=AsyncMock(side_effect=error))
    message = make_message(json.dumps({"ticket_id": str(ticket_id)}).encode())

    with patch("app.messaging.rabbitmq.asyncio.sleep", new_callable=AsyncMock) as sleep:
        asyncio.run(RabbitMQTicketAnalysisConsumer(handler).process_message(message))

    handler.handle.assert_awaited_once_with(ticket_id)
    sleep.assert_not_awaited()
    message.ack.assert_not_awaited()
    message.reject.assert_awaited_once_with(requeue=False)


@pytest.mark.parametrize("error", [LLMTimeoutError("timeout"), SQLAlchemyTimeoutError("pool")])
def test_transient_failure_retries_same_delivery_then_acks(error: Exception) -> None:
    ticket_id = uuid4()
    handler = SimpleNamespace(handle=AsyncMock(side_effect=[error, None]))
    message = make_message(json.dumps({"ticket_id": str(ticket_id)}).encode())

    with patch("app.messaging.rabbitmq.asyncio.sleep", new_callable=AsyncMock) as sleep:
        asyncio.run(RabbitMQTicketAnalysisConsumer(handler).process_message(message))

    assert handler.handle.await_count == 2
    sleep.assert_awaited_once_with(3)
    message.ack.assert_awaited_once_with()
    message.reject.assert_not_awaited()


def test_exhausted_transient_failure_rejects_to_dlq() -> None:
    ticket_id = uuid4()
    handler = SimpleNamespace(handle=AsyncMock(side_effect=SQLAlchemyTimeoutError("pool")))
    message = make_message(json.dumps({"ticket_id": str(ticket_id)}).encode())

    with patch("app.messaging.rabbitmq.asyncio.sleep", new_callable=AsyncMock) as sleep:
        asyncio.run(RabbitMQTicketAnalysisConsumer(handler).process_message(message))

    assert handler.handle.await_count == 3
    assert sleep.await_count == 2
    message.ack.assert_not_awaited()
    message.reject.assert_awaited_once_with(requeue=False)
