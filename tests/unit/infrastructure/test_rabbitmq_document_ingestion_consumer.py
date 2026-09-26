import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from app.messaging.rabbitmq import RabbitMQDocumentIngestionConsumer


def make_message(body: bytes) -> MagicMock:
    message = MagicMock()
    message.body = body
    message.message_id = "message-1"
    message.ack = AsyncMock()
    message.nack = AsyncMock()
    message.reject = AsyncMock()
    return message


def test_process_message_calls_handler_before_acknowledging() -> None:
    document_id = uuid4()
    message = make_message(json.dumps({"document_id": str(document_id)}).encode())
    handler = MagicMock()

    async def handle(received_id: object) -> None:
        assert received_id == document_id
        message.ack.assert_not_awaited()

    handler.handle = AsyncMock(side_effect=handle)

    asyncio.run(RabbitMQDocumentIngestionConsumer(handler).process_message(message))

    handler.handle.assert_awaited_once_with(document_id)
    message.ack.assert_awaited_once_with()
    message.nack.assert_not_awaited()
    message.reject.assert_not_awaited()


def test_process_message_logs_and_propagates_handler_error_without_settling_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    document_id = uuid4()
    message = make_message(json.dumps({"document_id": str(document_id)}).encode())
    handler = MagicMock()
    handler.handle = AsyncMock(side_effect=RuntimeError("ingestion failed"))

    with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError, match="ingestion failed"):
        asyncio.run(RabbitMQDocumentIngestionConsumer(handler).process_message(message))

    handler.handle.assert_awaited_once_with(document_id)
    assert "Failed to process document ingestion message message-1" in caplog.text
    message.ack.assert_not_awaited()
    message.nack.assert_not_awaited()
    message.reject.assert_not_awaited()


def test_process_message_logs_invalid_body_without_calling_handler_or_settling_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    message = make_message(b'{"document_id": "not-a-uuid"}')
    handler = MagicMock()
    handler.handle = AsyncMock()

    with caplog.at_level(logging.ERROR), pytest.raises(ValueError):
        asyncio.run(RabbitMQDocumentIngestionConsumer(handler).process_message(message))

    handler.handle.assert_not_awaited()
    assert "Failed to process document ingestion message message-1" in caplog.text
    message.ack.assert_not_awaited()
    message.nack.assert_not_awaited()
    message.reject.assert_not_awaited()
