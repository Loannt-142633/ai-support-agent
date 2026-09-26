"""Verify document ingestion messages against a real RabbitMQ broker."""

import asyncio
import json
from uuid import uuid4

import aio_pika
import pytest
from app.core.config import get_settings
from app.messaging.rabbitmq import RabbitMQDocumentIngestionPublisher


@pytest.mark.integration
def test_publishes_document_id_to_rabbitmq() -> None:
    settings = get_settings()
    document_id = uuid4()
    queue_name = f"document.ingestion.integration.{uuid4().hex}"

    async def publish_and_consume() -> None:
        publisher = RabbitMQDocumentIngestionPublisher(
            url=settings.rabbitmq_url,
            queue_name=queue_name,
        )
        await publisher.publish(document_id)

        connection = await aio_pika.connect_robust(settings.rabbitmq_url, timeout=5)
        async with connection:
            channel = await connection.channel()
            queue = await channel.declare_queue(queue_name, durable=True)
            try:
                message = await queue.get(timeout=5)
                assert message is not None
                assert json.loads(message.body) == {"document_id": str(document_id)}
                assert message.delivery_mode == aio_pika.DeliveryMode.PERSISTENT
                await message.ack()
            finally:
                await queue.delete()

    asyncio.run(publish_and_consume())
