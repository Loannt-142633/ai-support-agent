"""Kafka analysis completion handling and Redis publish ordering."""

import asyncio
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from aiokafka.structs import TopicPartition
from app.kafka_worker import run_worker
from app.messaging.kafka import (
    decode_analysis_completed,
    encode_analysis_completed,
    log_analysis_completed,
)
from app.services.analysis_completed_publisher import AnalysisCompleted


def _message(event: AnalysisCompleted) -> SimpleNamespace:
    return SimpleNamespace(
        topic="analysis.completed",
        key=str(event.ticket_id).encode(),
        value=encode_analysis_completed(event),
        partition=1,
        offset=7,
    )


def test_metrics_logs_and_commits_analysis_event(caplog: pytest.LogCaptureFixture) -> None:
    event = AnalysisCompleted(ticket_id=uuid4(), analysis_id=uuid4())
    consumer = Mock(commit=AsyncMock())
    with caplog.at_level(logging.INFO, logger="app.messaging.kafka"):
        asyncio.run(log_analysis_completed(consumer, _message(event), group_id="ticket-metrics"))
    assert f"ticket_id={event.ticket_id} analysis_id={event.analysis_id}" in caplog.text
    consumer.commit.assert_awaited_once_with({TopicPartition("analysis.completed", 1): 8})


def test_bad_key_never_commits() -> None:
    event = AnalysisCompleted(ticket_id=uuid4(), analysis_id=uuid4())
    message = _message(event)
    message.key = b"wrong"
    consumer = Mock(commit=AsyncMock())
    with pytest.raises(ValueError, match="Invalid analysis.completed event"):
        asyncio.run(log_analysis_completed(consumer, message, group_id="ticket-metrics"))
    consumer.commit.assert_not_awaited()


def test_invalid_analysis_id_rejected() -> None:
    event = AnalysisCompleted(ticket_id=uuid4(), analysis_id=uuid4())
    payload = json.dumps({"version": 1, "ticket_id": str(event.ticket_id), "analysis_id": "bad"})
    with pytest.raises(ValueError, match="Invalid analysis.completed event"):
        decode_analysis_completed(payload.encode(), str(event.ticket_id).encode())


@pytest.mark.parametrize("publish_fails", [False, True])
def test_notification_worker_commits_only_after_redis_publish(publish_fails: bool) -> None:
    event = AnalysisCompleted(ticket_id=uuid4(), analysis_id=uuid4())
    stop_event = asyncio.Event()
    consumer = Mock(start=AsyncMock(), stop=AsyncMock(), commit=AsyncMock())
    redis = Mock(aclose=AsyncMock())
    operations: list[str] = []

    async def getmany(**_kwargs: object) -> dict[TopicPartition, list[SimpleNamespace]]:
        stop_event.set()
        return {TopicPartition("analysis.completed", 1): [_message(event)]}

    async def publish(_event: AnalysisCompleted) -> None:
        operations.append("publish")
        if publish_fails:
            raise ConnectionError("Redis unavailable")

    async def commit(_offsets: object) -> None:
        operations.append("commit")

    consumer.getmany = AsyncMock(side_effect=getmany)
    consumer.commit.side_effect = commit
    settings = SimpleNamespace(
        ticket_created_topic="ticket.created",
        analysis_completed_topic="analysis.completed",
        kafka_bootstrap_servers="localhost:9092",
        redis_url="redis://localhost:6379/0",
        redis_notification_channel="ticket.notifications",
    )
    with (
        patch("app.kafka_worker.AIOKafkaConsumer", return_value=consumer),
        patch("app.kafka_worker.get_settings", return_value=settings),
        patch("app.kafka_worker.Redis.from_url", return_value=redis),
        patch("app.kafka_worker.RedisAnalysisNotificationPublisher") as publisher_class,
    ):
        publisher_class.return_value.publish = AsyncMock(side_effect=publish)
        if publish_fails:
            with pytest.raises(ConnectionError, match="Redis unavailable"):
                asyncio.run(run_worker("ticket-notifications", stop_event))
        else:
            asyncio.run(run_worker("ticket-notifications", stop_event))
        publisher_class.assert_called_once_with(redis, channel="ticket.notifications")
        publisher_class.return_value.publish.assert_awaited_once_with(event)

    assert operations == (["publish"] if publish_fails else ["publish", "commit"])
    if publish_fails:
        consumer.commit.assert_not_awaited()
    else:
        consumer.commit.assert_awaited_once_with({TopicPartition("analysis.completed", 1): 8})
    consumer.stop.assert_awaited_once()
    redis.aclose.assert_awaited_once()
