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
from app.services.analysis_completed_publisher import AnalysisCompleted
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError


def make_message(body: bytes) -> SimpleNamespace:
    return SimpleNamespace(
        body=body, message_id="delivery-1", ack=AsyncMock(), reject=AsyncMock(), nack=AsyncMock()
    )


def make_consumer(
    handler: SimpleNamespace,
) -> tuple[RabbitMQTicketAnalysisConsumer, SimpleNamespace]:
    publisher = SimpleNamespace(publish=AsyncMock())
    return RabbitMQTicketAnalysisConsumer(handler, publisher), publisher


def test_success_acks_once() -> None:
    ticket_id = uuid4()
    completed = AnalysisCompleted(ticket_id=ticket_id, analysis_id=uuid4())
    handler = SimpleNamespace(handle=AsyncMock(return_value=completed))
    message = make_message(json.dumps({"ticket_id": str(ticket_id)}).encode())
    consumer, publisher = make_consumer(handler)
    steps: list[str] = []

    async def publish(_event: AnalysisCompleted) -> None:
        steps.append("publish")

    async def ack() -> None:
        steps.append("ack")

    publisher.publish.side_effect = publish
    message.ack.side_effect = ack

    asyncio.run(consumer.process_message(message))

    handler.handle.assert_awaited_once_with(ticket_id)
    publisher.publish.assert_awaited_once_with(completed)
    message.ack.assert_awaited_once_with()
    message.reject.assert_not_awaited()
    message.nack.assert_not_awaited()
    assert steps == ["publish", "ack"]


@pytest.mark.parametrize(
    "body",
    [b"not json", b"[]", b"{}", b'{"ticket_id":123}', b'{"ticket_id":"bad"}'],
)
def test_invalid_payload_rejects_without_calling_handler(body: bytes) -> None:
    handler = SimpleNamespace(handle=AsyncMock())
    message = make_message(body)
    consumer, publisher = make_consumer(handler)

    asyncio.run(consumer.process_message(message))

    handler.handle.assert_not_awaited()
    publisher.publish.assert_not_awaited()
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
    consumer, publisher = make_consumer(handler)

    with patch("app.messaging.rabbitmq.asyncio.sleep", new_callable=AsyncMock) as sleep:
        asyncio.run(consumer.process_message(message))

    handler.handle.assert_awaited_once_with(ticket_id)
    publisher.publish.assert_not_awaited()
    sleep.assert_not_awaited()
    message.ack.assert_not_awaited()
    message.reject.assert_awaited_once_with(requeue=False)


@pytest.mark.parametrize("error", [LLMTimeoutError("timeout"), SQLAlchemyTimeoutError("pool")])
def test_transient_failure_retries_same_delivery_then_acks(error: Exception) -> None:
    ticket_id = uuid4()
    completed = AnalysisCompleted(ticket_id=ticket_id, analysis_id=uuid4())
    handler = SimpleNamespace(handle=AsyncMock(side_effect=[error, completed]))
    message = make_message(json.dumps({"ticket_id": str(ticket_id)}).encode())
    consumer, publisher = make_consumer(handler)

    with patch("app.messaging.rabbitmq.asyncio.sleep", new_callable=AsyncMock) as sleep:
        asyncio.run(consumer.process_message(message))

    assert handler.handle.await_count == 2
    publisher.publish.assert_awaited_once_with(completed)
    sleep.assert_awaited_once_with(3)
    message.ack.assert_awaited_once_with()
    message.reject.assert_not_awaited()


def test_exhausted_transient_failure_rejects_to_dlq() -> None:
    ticket_id = uuid4()
    handler = SimpleNamespace(handle=AsyncMock(side_effect=SQLAlchemyTimeoutError("pool")))
    message = make_message(json.dumps({"ticket_id": str(ticket_id)}).encode())
    consumer, publisher = make_consumer(handler)

    with patch("app.messaging.rabbitmq.asyncio.sleep", new_callable=AsyncMock) as sleep:
        asyncio.run(consumer.process_message(message))

    assert handler.handle.await_count == 3
    publisher.publish.assert_not_awaited()
    assert sleep.await_count == 2
    message.ack.assert_not_awaited()
    message.reject.assert_awaited_once_with(requeue=False)


def test_kafka_publish_failure_requeues_without_ack_or_reanalysis() -> None:
    ticket_id = uuid4()
    completed = AnalysisCompleted(ticket_id=ticket_id, analysis_id=uuid4())
    handler = SimpleNamespace(handle=AsyncMock(return_value=completed))
    message = make_message(json.dumps({"ticket_id": str(ticket_id)}).encode())
    consumer, publisher = make_consumer(handler)
    publisher.publish.side_effect = ConnectionError("Kafka unavailable")

    with patch("app.messaging.rabbitmq.asyncio.sleep", new_callable=AsyncMock) as sleep:
        asyncio.run(consumer.process_message(message))

    handler.handle.assert_awaited_once_with(ticket_id)
    assert publisher.publish.await_count == 3
    assert sleep.await_count == 2
    message.nack.assert_awaited_once_with(requeue=True)
    message.ack.assert_not_awaited()
    message.reject.assert_not_awaited()


def test_kafka_publish_retry_succeeds_before_ack() -> None:
    ticket_id = uuid4()
    completed = AnalysisCompleted(ticket_id=ticket_id, analysis_id=uuid4())
    handler = SimpleNamespace(handle=AsyncMock(return_value=completed))
    message = make_message(json.dumps({"ticket_id": str(ticket_id)}).encode())
    consumer, publisher = make_consumer(handler)
    publisher.publish.side_effect = [ConnectionError("temporary"), None]

    with patch("app.messaging.rabbitmq.asyncio.sleep", new_callable=AsyncMock) as sleep:
        asyncio.run(consumer.process_message(message))

    handler.handle.assert_awaited_once_with(ticket_id)
    assert publisher.publish.await_count == 2
    sleep.assert_awaited_once_with(3)
    message.ack.assert_awaited_once_with()
    message.nack.assert_not_awaited()
