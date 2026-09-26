"""RabbitMQ publisher for document ingestion jobs."""

import json
from uuid import UUID

import aio_pika


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
