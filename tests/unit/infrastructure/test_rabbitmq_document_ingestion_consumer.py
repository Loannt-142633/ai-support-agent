import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from app.jobs.document_ingestion_handler import DocumentNotFoundError
from app.messaging.rabbitmq import RabbitMQDocumentIngestionConsumer


def make_message(body: bytes) -> MagicMock:
    message = MagicMock()
    message.body = body
    message.message_id = "message-1"
    message.ack = AsyncMock()
    message.nack = AsyncMock()
    message.reject = AsyncMock()
    return message


def test_process_message_logs_completion_after_acknowledging(
    caplog: pytest.LogCaptureFixture,
) -> None:
    document_id = uuid4()
    message = make_message(json.dumps({"document_id": str(document_id)}).encode())
    handler = MagicMock()

    async def handle(received_id: object) -> None:
        assert received_id == document_id
        message.ack.assert_not_awaited()

    handler.handle = AsyncMock(side_effect=handle)

    with caplog.at_level(logging.INFO):
        asyncio.run(RabbitMQDocumentIngestionConsumer(handler).process_message(message))

    handler.handle.assert_awaited_once_with(document_id)
    message.ack.assert_awaited_once_with()
    message.nack.assert_not_awaited()
    message.reject.assert_not_awaited()
    assert (
        f"Document ingestion completed; ACK sent for document_id={document_id} "
        "message_id=message-1"
    ) in caplog.text


def test_process_message_does_not_log_completion_when_ack_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    document_id = uuid4()
    message = make_message(json.dumps({"document_id": str(document_id)}).encode())
    message.ack.side_effect = RuntimeError("ack failed")
    handler = MagicMock()
    handler.handle = AsyncMock()

    with caplog.at_level(logging.INFO), pytest.raises(RuntimeError, match="ack failed"):
        asyncio.run(RabbitMQDocumentIngestionConsumer(handler).process_message(message))

    handler.handle.assert_awaited_once_with(document_id)
    message.ack.assert_awaited_once_with()
    assert "Document ingestion completed" not in caplog.text


def test_process_message_rejects_missing_document_without_requeue(
    caplog: pytest.LogCaptureFixture,
) -> None:
    document_id = uuid4()
    message = make_message(json.dumps({"document_id": str(document_id)}).encode())
    handler = MagicMock()
    handler.handle = AsyncMock(side_effect=DocumentNotFoundError(document_id))

    with caplog.at_level(logging.ERROR):
        asyncio.run(RabbitMQDocumentIngestionConsumer(handler).process_message(message))

    handler.handle.assert_awaited_once_with(document_id)
    assert f"Document {document_id} not found for ingestion message message-1" in caplog.text
    message.ack.assert_not_awaited()
    message.nack.assert_not_awaited()
    message.reject.assert_awaited_once_with(requeue=False)


def test_process_message_rejects_handler_error_for_dead_lettering(
    caplog: pytest.LogCaptureFixture,
) -> None:
    document_id = uuid4()
    message = make_message(json.dumps({"document_id": str(document_id)}).encode())
    handler = MagicMock()
    handler.handle = AsyncMock(side_effect=RuntimeError("ingestion failed"))

    with caplog.at_level(logging.ERROR):
        asyncio.run(RabbitMQDocumentIngestionConsumer(handler).process_message(message))

    handler.handle.assert_awaited_once_with(document_id)
    assert f"Failed to ingest document {document_id} from message message-1" in caplog.text
    message.ack.assert_not_awaited()
    message.nack.assert_not_awaited()
    message.reject.assert_awaited_once_with(requeue=False)


@pytest.mark.parametrize(
    "body",
    [
        b'{"document_id": "not-a-uuid"}',
        b"{}",
        b"not-json",
    ],
)
def test_process_message_rejects_invalid_body_without_calling_handler(
    body: bytes,
    caplog: pytest.LogCaptureFixture,
) -> None:
    message = make_message(body)
    handler = MagicMock()
    handler.handle = AsyncMock()

    with caplog.at_level(logging.ERROR):
        asyncio.run(RabbitMQDocumentIngestionConsumer(handler).process_message(message))

    handler.handle.assert_not_awaited()
    assert "Invalid document ingestion message message-1" in caplog.text
    message.ack.assert_not_awaited()
    message.nack.assert_not_awaited()
    message.reject.assert_awaited_once_with(requeue=False)
