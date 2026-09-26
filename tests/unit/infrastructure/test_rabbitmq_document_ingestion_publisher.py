import asyncio
import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import aio_pika
import pytest
from app.api.dependencies import get_document_ingestion_publisher
from app.messaging.rabbitmq import RabbitMQDocumentIngestionPublisher


def test_publish_sends_persistent_document_id_to_durable_queue() -> None:
    document_id = uuid4()
    connection = AsyncMock()
    connection.__aenter__.return_value = connection
    channel = AsyncMock()
    connection.channel.return_value = channel

    with patch(
        "app.messaging.rabbitmq.aio_pika.connect_robust", new_callable=AsyncMock
    ) as connect:
        connect.return_value = connection
        asyncio.run(
            RabbitMQDocumentIngestionPublisher(
                url="amqp://app:app@localhost:5672/",
                queue_name="document.ingestion",
            ).publish(document_id)
        )

    connect.assert_awaited_once_with("amqp://app:app@localhost:5672/", timeout=5)
    connection.channel.assert_awaited_once_with(
        publisher_confirms=True, on_return_raises=True
    )
    channel.declare_queue.assert_awaited_once_with("document.ingestion", durable=True)
    channel.default_exchange.publish.assert_awaited_once()
    message = channel.default_exchange.publish.await_args.args[0]
    assert json.loads(message.body) == {"document_id": str(document_id)}
    assert message.content_type == "application/json"
    assert message.delivery_mode == aio_pika.DeliveryMode.PERSISTENT
    assert message.message_id == str(document_id)
    assert channel.default_exchange.publish.await_args.kwargs == {
        "routing_key": "document.ingestion",
        "mandatory": True,
    }
    connection.__aexit__.assert_awaited_once()


def test_document_ingestion_dependency_uses_rabbitmq() -> None:
    assert isinstance(
        get_document_ingestion_publisher(), RabbitMQDocumentIngestionPublisher
    )


@pytest.mark.parametrize(
    ("url", "queue_name"),
    [("", "document.ingestion"), ("amqp://localhost/", " ")],
)
def test_rejects_blank_connection_settings(url: str, queue_name: str) -> None:
    with pytest.raises(ValueError):
        RabbitMQDocumentIngestionPublisher(url=url, queue_name=queue_name)
