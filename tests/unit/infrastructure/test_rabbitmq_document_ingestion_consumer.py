import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import psycopg
import pytest
from app.jobs.document_ingestion_handler import DocumentNotFoundError
from app.messaging.rabbitmq import RabbitMQDocumentIngestionConsumer
from app.models.document import DocumentStatus
from app.parsers.document import DocumentParseError
from app.services.document_ingestion_service import NoExtractableTextError
from pypdf.errors import PdfReadError
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError


def make_message(body: bytes) -> MagicMock:
    message = MagicMock()
    message.body = body
    message.message_id = "message-1"
    message.ack = AsyncMock()
    message.nack = AsyncMock()
    message.reject = AsyncMock()
    return message


def make_connection_error() -> OperationalError:
    return OperationalError(
        "SELECT documents.id FROM documents",
        {},
        psycopg.OperationalError("connection refused"),
    )


def make_parse_error(cause: Exception) -> DocumentParseError:
    try:
        raise DocumentParseError("Could not parse PDF document") from cause
    except DocumentParseError as error:
        return error


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
        f"Document ingestion completed; ACK sent for document_id={document_id} message_id=message-1"
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
    handler.mark_failed = AsyncMock(return_value=DocumentStatus.FAILED)

    with caplog.at_level(logging.ERROR):
        asyncio.run(RabbitMQDocumentIngestionConsumer(handler).process_message(message))

    handler.handle.assert_awaited_once_with(document_id)
    handler.mark_failed.assert_awaited_once_with(
        document_id, "Document ingestion failed (RuntimeError)"
    )
    assert f"Failed to ingest document {document_id} from message message-1" in caplog.text
    message.ack.assert_not_awaited()
    message.nack.assert_not_awaited()
    message.reject.assert_awaited_once_with(requeue=False)


@pytest.mark.parametrize("failed_attempts", [1, 2])
def test_process_message_retries_db_connection_without_settling_delivery(
    failed_attempts: int,
) -> None:
    document_id = uuid4()
    message = make_message(json.dumps({"document_id": str(document_id)}).encode())
    events: list[str] = []
    handler = MagicMock()

    async def handle(received_id: object) -> None:
        assert received_id == document_id
        events.append("handle")
        if events.count("handle") <= failed_attempts:
            raise make_connection_error()

    async def sleep(seconds: int) -> None:
        assert seconds == 3
        events.append("sleep")
        message.ack.assert_not_awaited()
        message.reject.assert_not_awaited()
        message.nack.assert_not_awaited()

    async def ack() -> None:
        events.append("ack")

    handler.handle = AsyncMock(side_effect=handle)
    message.ack.side_effect = ack
    with patch(
        "app.messaging.rabbitmq.asyncio.sleep", new=AsyncMock(side_effect=sleep)
    ) as sleep_mock:
        asyncio.run(RabbitMQDocumentIngestionConsumer(handler).process_message(message))

    assert handler.handle.await_count == failed_attempts + 1
    assert sleep_mock.await_count == failed_attempts
    assert events == ["handle", "sleep"] * failed_attempts + ["handle", "ack"]
    message.ack.assert_awaited_once_with()
    message.reject.assert_not_awaited()
    message.nack.assert_not_awaited()


def test_process_message_rejects_after_three_db_checkout_failures(
    caplog: pytest.LogCaptureFixture,
) -> None:
    document_id = uuid4()
    message = make_message(json.dumps({"document_id": str(document_id)}).encode())
    handler = MagicMock()
    handler.handle = AsyncMock(side_effect=SQLAlchemyTimeoutError("DB pool exhausted"))
    handler.mark_failed = AsyncMock(return_value=DocumentStatus.FAILED)

    async def sleep(seconds: int) -> None:
        assert seconds == 3
        message.ack.assert_not_awaited()
        message.reject.assert_not_awaited()
        message.nack.assert_not_awaited()
        handler.mark_failed.assert_not_awaited()

    with (
        caplog.at_level(logging.ERROR),
        patch(
            "app.messaging.rabbitmq.asyncio.sleep", new=AsyncMock(side_effect=sleep)
        ) as sleep_mock,
    ):
        asyncio.run(RabbitMQDocumentIngestionConsumer(handler).process_message(message))

    assert handler.handle.await_count == 3
    assert sleep_mock.await_count == 2
    handler.mark_failed.assert_awaited_once_with(
        document_id, "Temporary infrastructure failure after 3 attempts"
    )
    message.ack.assert_not_awaited()
    message.nack.assert_not_awaited()
    message.reject.assert_awaited_once_with(requeue=False)
    assert (
        f"Failed to ingest document {document_id} from message message-1 after 3 attempt(s)"
    ) in caplog.text


@pytest.mark.parametrize(
    "connection_error",
    [
        OperationalError("SELECT 1", {}, psycopg.errors.ConnectionFailure("connection lost")),
        OperationalError(
            "SELECT 1",
            {},
            RuntimeError("connection invalidated"),
            connection_invalidated=True,
        ),
    ],
)
def test_process_message_retries_confirmed_db_connection_failures(
    connection_error: OperationalError,
) -> None:
    document_id = uuid4()
    message = make_message(json.dumps({"document_id": str(document_id)}).encode())
    handler = MagicMock()
    handler.handle = AsyncMock(side_effect=[connection_error, None])

    with patch("app.messaging.rabbitmq.asyncio.sleep", new_callable=AsyncMock) as sleep_mock:
        asyncio.run(RabbitMQDocumentIngestionConsumer(handler).process_message(message))

    assert handler.handle.await_count == 2
    sleep_mock.assert_awaited_once_with(3)
    message.ack.assert_awaited_once_with()
    message.reject.assert_not_awaited()
    message.nack.assert_not_awaited()


@pytest.mark.parametrize(
    "error",
    [
        NoExtractableTextError("no text"),
        make_parse_error(PdfReadError("invalid PDF")),
        make_parse_error(FileNotFoundError("missing file")),
        OperationalError(
            "SELECT 1", {}, psycopg.errors.SerializationFailure("serialization failure")
        ),
    ],
)
def test_process_message_rejects_non_connection_failures_without_retry(
    error: Exception,
) -> None:
    document_id = uuid4()
    message = make_message(json.dumps({"document_id": str(document_id)}).encode())
    handler = MagicMock()
    handler.handle = AsyncMock(side_effect=error)
    handler.mark_failed = AsyncMock(return_value=DocumentStatus.FAILED)

    with patch("app.messaging.rabbitmq.asyncio.sleep", new_callable=AsyncMock) as sleep_mock:
        asyncio.run(RabbitMQDocumentIngestionConsumer(handler).process_message(message))

    handler.handle.assert_awaited_once_with(document_id)
    assert handler.mark_failed.await_count == 1
    assert handler.mark_failed.await_args.args[0] == document_id
    assert len(handler.mark_failed.await_args.args[1]) <= 255
    sleep_mock.assert_not_awaited()
    message.ack.assert_not_awaited()
    message.nack.assert_not_awaited()
    message.reject.assert_awaited_once_with(requeue=False)


def test_process_message_acks_if_failed_attempt_already_persisted_chunks() -> None:
    document_id = uuid4()
    message = make_message(json.dumps({"document_id": str(document_id)}).encode())
    handler = MagicMock()
    handler.handle = AsyncMock(side_effect=RuntimeError("commit reply lost"))
    handler.mark_failed = AsyncMock(return_value=DocumentStatus.COMPLETED)

    asyncio.run(RabbitMQDocumentIngestionConsumer(handler).process_message(message))

    handler.mark_failed.assert_awaited_once()
    message.ack.assert_awaited_once_with()
    message.reject.assert_not_awaited()


def test_process_message_rejects_when_failed_status_cannot_be_persisted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    document_id = uuid4()
    message = make_message(json.dumps({"document_id": str(document_id)}).encode())
    handler = MagicMock()
    handler.handle = AsyncMock(side_effect=RuntimeError("ingestion failed"))
    handler.mark_failed = AsyncMock(side_effect=SQLAlchemyTimeoutError("DB unavailable"))

    with caplog.at_level(logging.ERROR):
        asyncio.run(RabbitMQDocumentIngestionConsumer(handler).process_message(message))

    assert "Could not persist failed status" in caplog.text
    handler.mark_failed.assert_awaited_once()
    message.ack.assert_not_awaited()
    message.reject.assert_awaited_once_with(requeue=False)


def test_process_message_retries_parse_error_only_for_connection_cause() -> None:
    document_id = uuid4()
    message = make_message(json.dumps({"document_id": str(document_id)}).encode())
    handler = MagicMock()
    handler.handle = AsyncMock(
        side_effect=[make_parse_error(ConnectionResetError("remote read lost")), None]
    )

    with patch("app.messaging.rabbitmq.asyncio.sleep", new_callable=AsyncMock) as sleep_mock:
        asyncio.run(RabbitMQDocumentIngestionConsumer(handler).process_message(message))

    assert handler.handle.await_count == 2
    sleep_mock.assert_awaited_once_with(3)
    message.ack.assert_awaited_once_with()
    message.nack.assert_not_awaited()
    message.reject.assert_not_awaited()


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
