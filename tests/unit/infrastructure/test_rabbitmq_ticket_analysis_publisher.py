"""Verify persistent ticket analysis jobs are published to RabbitMQ."""

import asyncio
import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import aio_pika
import pytest
from app.api.dependencies import get_ticket_analysis_publisher
from app.messaging.rabbitmq import RabbitMQTicketAnalysisPublisher


def test_publish_sends_persistent_ticket_id_to_durable_queue() -> None:
    ticket_id = uuid4()
    connection = AsyncMock()
    connection.__aenter__.return_value = connection
    channel = AsyncMock()
    connection.channel.return_value = channel

    with patch("app.messaging.rabbitmq.aio_pika.connect_robust", new_callable=AsyncMock) as connect:
        connect.return_value = connection
        asyncio.run(
            RabbitMQTicketAnalysisPublisher(
                url="amqp://app:app@localhost:5672/",
                queue_name="ticket.analysis",
            ).publish(ticket_id)
        )

    connect.assert_awaited_once_with("amqp://app:app@localhost:5672/", timeout=5)
    connection.channel.assert_awaited_once_with(publisher_confirms=True, on_return_raises=True)
    channel.declare_queue.assert_awaited_once_with("ticket.analysis", durable=True)
    channel.default_exchange.publish.assert_awaited_once()
    message = channel.default_exchange.publish.await_args.args[0]
    assert json.loads(message.body) == {"ticket_id": str(ticket_id)}
    assert message.content_type == "application/json"
    assert message.delivery_mode == aio_pika.DeliveryMode.PERSISTENT
    assert message.message_id == str(ticket_id)
    assert channel.default_exchange.publish.await_args.kwargs == {
        "routing_key": "ticket.analysis",
        "mandatory": True,
    }
    connection.__aexit__.assert_awaited_once()


def test_ticket_analysis_dependency_uses_rabbitmq() -> None:
    assert isinstance(get_ticket_analysis_publisher(), RabbitMQTicketAnalysisPublisher)


@pytest.mark.parametrize(
    ("url", "queue_name"),
    [("", "ticket.analysis"), ("amqp://localhost/", " ")],
)
def test_rejects_blank_connection_settings(url: str, queue_name: str) -> None:
    with pytest.raises(ValueError):
        RabbitMQTicketAnalysisPublisher(url=url, queue_name=queue_name)
