"""Kafka analysis.completed message contract."""

import asyncio
import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.messaging.kafka import KafkaAnalysisCompletedPublisher
from app.services.analysis_completed_publisher import AnalysisCompleted


def test_publishes_committed_analysis_with_ticket_id_key() -> None:
    event = AnalysisCompleted(ticket_id=uuid4(), analysis_id=uuid4())
    producer = AsyncMock()
    with patch("app.messaging.kafka.AIOKafkaProducer", return_value=producer) as factory:
        asyncio.run(
            KafkaAnalysisCompletedPublisher(
                bootstrap_servers="localhost:9092", topic="analysis.completed"
            ).publish(event)
        )

    factory.assert_called_once_with(
        bootstrap_servers="localhost:9092", acks="all", enable_idempotence=True
    )
    producer.start.assert_awaited_once()
    producer.send_and_wait.assert_awaited_once()
    args, kwargs = producer.send_and_wait.await_args
    assert args == ("analysis.completed",)
    assert kwargs["key"] == str(event.ticket_id).encode("utf-8")
    assert json.loads(kwargs["value"]) == {
        "version": 1,
        "ticket_id": str(event.ticket_id),
        "analysis_id": str(event.analysis_id),
    }
    producer.stop.assert_awaited_once()


def test_publish_failure_closes_producer() -> None:
    producer = AsyncMock()
    producer.send_and_wait.side_effect = ConnectionError("Kafka unavailable")
    with patch("app.messaging.kafka.AIOKafkaProducer", return_value=producer):
        try:
            asyncio.run(
                KafkaAnalysisCompletedPublisher(
                    bootstrap_servers="localhost:9092", topic="analysis.completed"
                ).publish(AnalysisCompleted(ticket_id=uuid4(), analysis_id=uuid4()))
            )
        except ConnectionError as error:
            assert str(error) == "Kafka unavailable"
        else:
            raise AssertionError("Expected Kafka publish failure")

    producer.stop.assert_awaited_once()
