"""RabbitMQ messaging for document ingestion jobs."""

import json
import logging
from uuid import UUID

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from app.jobs.document_ingestion_handler import DocumentIngestionJobHandler

logger = logging.getLogger(__name__)


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
            channel = await connection.channel(
                publisher_confirms=True, on_return_raises=True
            )
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


class RabbitMQDocumentIngestionConsumer:
    """Process one delivered ingestion message using an injected job handler."""

    def __init__(self, handler: DocumentIngestionJobHandler) -> None:
        self._handler = handler

    async def process_message(self, message: AbstractIncomingMessage) -> None:
        """Acknowledge only after ingestion succeeds; leave failure policy to caller."""

        try:
            payload = json.loads(message.body)
            if not isinstance(payload, dict) or not isinstance(
                payload.get("document_id"), str
            ):
                raise ValueError("Invalid document ingestion message")

            document_id = UUID(payload["document_id"])
            await self._handler.handle(document_id)
            await message.ack()
        except Exception:
            logger.exception(
                "Failed to process document ingestion message %s", message.message_id
            )
            raise
