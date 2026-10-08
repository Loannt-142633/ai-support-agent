"""RabbitMQ messaging for document ingestion jobs."""

import asyncio
import json
import logging
from uuid import UUID

import aio_pika
import psycopg
from aio_pika.abc import AbstractIncomingMessage
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from app.jobs.document_ingestion_handler import (
    DocumentIngestionJobHandler,
    DocumentNotFoundError,
)
from app.jobs.ticket_analysis_handler import TicketAnalysisJobHandler, TicketNotFoundError
from app.llm.exceptions import LLMRateLimitError, LLMTimeoutError
from app.models.document import DocumentStatus
from app.parsers.document import DocumentParseError
from app.services.analysis_completed_publisher import AnalysisCompletedPublisher
from app.services.document_ingestion_service import NoExtractableTextError

logger = logging.getLogger(__name__)
_MAX_HANDLER_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 3
_RETRYABLE_SQLSTATES = {"53300", "57P01", "57P02", "57P03"}


def _failure_reason(error: Exception) -> str:
    """Return a short, non-sensitive reason for the status API."""

    if isinstance(error, NoExtractableTextError):
        return "Document has no extractable text"
    if _is_retryable_error(error):
        return "Temporary infrastructure failure after 3 attempts"
    if isinstance(error, DocumentParseError):
        return "PDF could not be parsed"
    return f"Document ingestion failed ({type(error).__name__})"[:255]


def _is_retryable_error(error: Exception) -> bool:
    """Retry only recognized connection/checkout failures, not bad documents."""

    if isinstance(error, DocumentParseError):
        # PDF syntax errors and missing/inaccessible files are not transient.
        return isinstance(error.__cause__, (ConnectionError, TimeoutError))
    if isinstance(error, SQLAlchemyTimeoutError):
        return True  # Timed out waiting for a DB connection from the pool.
    if not isinstance(error, DBAPIError):
        return False
    if error.connection_invalidated:
        return True

    sqlstate = getattr(error.orig, "sqlstate", None)
    if isinstance(sqlstate, str):
        return sqlstate.startswith("08") or sqlstate in _RETRYABLE_SQLSTATES
    # A failed initial connection often has no SQLSTATE and is not marked
    # invalidated because there was no established connection to invalidate.
    return isinstance(
        error.orig,
        (psycopg.OperationalError, psycopg.InterfaceError, ConnectionError, TimeoutError),
    )


class RabbitMQDocumentIngestionPublisher:
    """Publish persisted document IDs to a durable RabbitMQ queue."""

    def __init__(self, *, url: str, queue_name: str) -> None:
        if not url.strip():
            raise ValueError("RabbitMQ URL must not be empty")
        if not queue_name.strip():
            raise ValueError("RabbitMQ queue name must not be empty")
        self._url = url
        self._queue_name = queue_name

    async def publish(self, document_id: UUID) -> None:
        """Publish a persistent JSON job after document metadata is committed."""

        connection = await aio_pika.connect_robust(self._url, timeout=5)
        async with connection:
            channel = await connection.channel(publisher_confirms=True, on_return_raises=True)
            await channel.declare_queue(self._queue_name, durable=True)
            message = aio_pika.Message(
                body=json.dumps({"document_id": str(document_id)}).encode("utf-8"),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=str(document_id),
            )
            await channel.default_exchange.publish(
                message,
                routing_key=self._queue_name,
                mandatory=True,
            )


class RabbitMQTicketAnalysisPublisher:
    """Publish persisted ticket IDs to a durable RabbitMQ queue."""

    def __init__(self, *, url: str, queue_name: str) -> None:
        if not url.strip():
            raise ValueError("RabbitMQ URL must not be empty")
        if not queue_name.strip():
            raise ValueError("Ticket analysis queue name must not be empty")
        self._url = url
        self._queue_name = queue_name

    async def publish(self, ticket_id: UUID) -> None:
        """Publish a persistent JSON job after ticket metadata is committed."""

        connection = await aio_pika.connect_robust(self._url, timeout=5)
        async with connection:
            channel = await connection.channel(publisher_confirms=True, on_return_raises=True)
            await channel.declare_queue(self._queue_name, durable=True)
            message = aio_pika.Message(
                body=json.dumps({"ticket_id": str(ticket_id)}).encode("utf-8"),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=str(ticket_id),
            )
            await channel.default_exchange.publish(
                message,
                routing_key=self._queue_name,
                mandatory=True,
            )


class RabbitMQDocumentIngestionConsumer:
    """Process one delivered ingestion message using an injected job handler."""

    def __init__(self, handler: DocumentIngestionJobHandler) -> None:
        self._handler = handler

    async def process_message(self, message: AbstractIncomingMessage) -> None:
        """Retry transient failures while retaining delivery; then ACK or reject."""

        try:
            payload = json.loads(message.body)
            if not isinstance(payload, dict) or not isinstance(payload.get("document_id"), str):
                raise ValueError("Invalid document ingestion message")

            document_id = UUID(payload["document_id"])
        except (ValueError, UnicodeDecodeError):
            logger.exception("Invalid document ingestion message %s", message.message_id)
            await message.reject(requeue=False)
            return

        for attempt in range(1, _MAX_HANDLER_ATTEMPTS + 1):
            try:
                await self._handler.handle(document_id)
            except DocumentNotFoundError:
                logger.exception(
                    "Document %s not found for ingestion message %s",
                    document_id,
                    message.message_id,
                )
                await message.reject(requeue=False)
                return
            except Exception as error:
                if attempt < _MAX_HANDLER_ATTEMPTS and _is_retryable_error(error):
                    logger.warning(
                        "Transient ingestion failure for document %s from message %s "
                        "(attempt %s/%s); retrying in %s seconds: %s",
                        document_id,
                        message.message_id,
                        attempt,
                        _MAX_HANDLER_ATTEMPTS,
                        _RETRY_DELAY_SECONDS,
                        error,
                    )
                    await asyncio.sleep(_RETRY_DELAY_SECONDS)
                    continue
                logger.exception(
                    "Failed to ingest document %s from message %s after %s "
                    "attempt(s); rejecting without requeue",
                    document_id,
                    message.message_id,
                    attempt,
                )
                try:
                    final_status = await self._handler.mark_failed(
                        document_id, _failure_reason(error)
                    )
                except Exception:
                    logger.exception(
                        "Could not persist failed status for document %s from message %s",
                        document_id,
                        message.message_id,
                    )
                else:
                    if final_status == DocumentStatus.COMPLETED:
                        logger.info(
                            "Document %s already has chunks; acknowledging message %s",
                            document_id,
                            message.message_id,
                        )
                        break
                await message.reject(requeue=False)
                return
            else:
                break

        try:
            await message.ack()
        except Exception:
            logger.exception("Failed to ACK document ingestion message %s", message.message_id)
            raise
        logger.info(
            "Document ingestion completed; ACK sent for document_id=%s message_id=%s",
            document_id,
            message.message_id,
        )


class RabbitMQTicketAnalysisConsumer:
    """Analyze, publish completion, then settle the RabbitMQ delivery."""

    def __init__(
        self, handler: TicketAnalysisJobHandler, completed_publisher: AnalysisCompletedPublisher
    ) -> None:
        self._handler = handler
        self._completed_publisher = completed_publisher

    async def process_message(self, message: AbstractIncomingMessage) -> None:
        try:
            payload = json.loads(message.body)
            if not isinstance(payload, dict) or not isinstance(payload.get("ticket_id"), str):
                raise ValueError("Invalid ticket analysis message")
            ticket_id = UUID(payload["ticket_id"])
        except (ValueError, UnicodeDecodeError):
            logger.exception("Invalid ticket analysis message %s", message.message_id)
            await message.reject(requeue=False)
            return

        for attempt in range(1, _MAX_HANDLER_ATTEMPTS + 1):
            try:
                completed = await self._handler.handle(ticket_id)
            except TicketNotFoundError:
                logger.exception(
                    "Ticket %s not found for analysis message %s",
                    ticket_id,
                    message.message_id,
                )
                await message.reject(requeue=False)
                return
            except Exception as error:
                if attempt < _MAX_HANDLER_ATTEMPTS and (
                    _is_retryable_error(error)
                    or isinstance(error, (LLMTimeoutError, LLMRateLimitError))
                ):
                    logger.warning(
                        "Transient ticket analysis failure for %s (attempt %s/%s); "
                        "retrying in %s seconds",
                        ticket_id,
                        attempt,
                        _MAX_HANDLER_ATTEMPTS,
                        _RETRY_DELAY_SECONDS,
                        exc_info=True,
                    )
                    await asyncio.sleep(_RETRY_DELAY_SECONDS)
                    continue
                logger.exception(
                    "Failed to analyze ticket %s from message %s after %s attempt(s); "
                    "rejecting without requeue",
                    ticket_id,
                    message.message_id,
                    attempt,
                )
                await message.reject(requeue=False)
                return
            else:
                break

        for attempt in range(1, _MAX_HANDLER_ATTEMPTS + 1):
            try:
                await self._completed_publisher.publish(completed)
            except Exception:
                if attempt < _MAX_HANDLER_ATTEMPTS:
                    logger.warning(
                        "Could not publish analysis.completed for ticket %s "
                        "(attempt %s/%s); retrying in %s seconds",
                        ticket_id,
                        attempt,
                        _MAX_HANDLER_ATTEMPTS,
                        _RETRY_DELAY_SECONDS,
                        exc_info=True,
                    )
                    await asyncio.sleep(_RETRY_DELAY_SECONDS)
                    continue
                logger.exception(
                    "Could not publish analysis.completed for ticket %s; "
                    "requeueing RabbitMQ delivery",
                    ticket_id,
                )
                await message.nack(requeue=True)
                return
            else:
                break

        try:
            await message.ack()
        except Exception:
            logger.exception("Failed to ACK ticket analysis message %s", message.message_id)
            raise
        logger.info(
            "Ticket analysis completed; ACK sent for ticket_id=%s message_id=%s",
            ticket_id,
            message.message_id,
        )
