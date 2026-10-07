"""Kafka ticket-created message contract."""

import asyncio
import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.messaging.kafka import KafkaTicketCreatedPublisher
from app.services.ticket_created_publisher import TicketCreated


def test_publishes_ticket_id_as_key_with_broker_acknowledgement() -> None:
    ticket_id = uuid4()
    producer = AsyncMock()
    with patch("app.messaging.kafka.AIOKafkaProducer", return_value=producer) as factory:
        asyncio.run(
            KafkaTicketCreatedPublisher(
                bootstrap_servers="localhost:9092", topic="ticket.created"
            ).publish(TicketCreated(ticket_id=ticket_id))
        )

    factory.assert_called_once_with(
        bootstrap_servers="localhost:9092", acks="all", enable_idempotence=True
    )
    producer.start.assert_awaited_once()
    producer.send_and_wait.assert_awaited_once()
    args, kwargs = producer.send_and_wait.await_args
    assert args == ("ticket.created",)
    assert kwargs["key"] == str(ticket_id).encode("utf-8")
    assert json.loads(kwargs["value"]) == {"version": 1, "ticket_id": str(ticket_id)}
    producer.stop.assert_awaited_once()


def test_stops_producer_when_kafka_send_fails() -> None:
    producer = AsyncMock()
    producer.send_and_wait.side_effect = RuntimeError("send failed")
    with patch("app.messaging.kafka.AIOKafkaProducer", return_value=producer):
        try:
            asyncio.run(
                KafkaTicketCreatedPublisher(
                    bootstrap_servers="localhost:9092", topic="ticket.created"
                ).publish(TicketCreated(ticket_id=uuid4()))
            )
        except RuntimeError as error:
            assert str(error) == "send failed"
        else:
            raise AssertionError("Expected send failure")

    producer.stop.assert_awaited_once()
