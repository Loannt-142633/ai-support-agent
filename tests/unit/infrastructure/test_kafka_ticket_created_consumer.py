"""Ticket-created Kafka consumer contract and offset handling."""

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from aiokafka.structs import TopicPartition
from app.kafka_worker import run_worker
from app.messaging.kafka import encode_ticket_created, log_ticket_created
from app.services.ticket_created_publisher import TicketCreated


def _message(ticket: TicketCreated, *, partition: int = 2, offset: int = 8) -> SimpleNamespace:
    return SimpleNamespace(
        topic="ticket.created",
        key=str(ticket.ticket_id).encode("utf-8"),
        value=encode_ticket_created(ticket),
        partition=partition,
        offset=offset,
    )


@pytest.mark.parametrize("group_id", ["ticket-notifications", "ticket-metrics"])
def test_logs_event_before_committing_its_exact_offset(group_id: str, caplog) -> None:
    ticket = TicketCreated(ticket_id=uuid4())
    consumer = Mock()
    consumer.commit = AsyncMock()
    with caplog.at_level(logging.INFO, logger="app.messaging.kafka"):
        asyncio.run(log_ticket_created(consumer, _message(ticket), group_id=group_id))

    assert f"ticket_id={ticket.ticket_id} partition=2 offset=8 group_id={group_id}" in caplog.text
    consumer.commit.assert_awaited_once_with({TopicPartition("ticket.created", 2): 9})


def test_invalid_event_does_not_commit() -> None:
    consumer = Mock()
    consumer.commit = AsyncMock()
    message = _message(TicketCreated(ticket_id=uuid4()))
    message.key = b"different-ticket"

    with pytest.raises(ValueError, match="Invalid ticket.created event"):
        asyncio.run(log_ticket_created(consumer, message, group_id="ticket-metrics"))

    consumer.commit.assert_not_awaited()


def test_logging_failure_does_not_commit() -> None:
    consumer = Mock()
    consumer.commit = AsyncMock()
    with patch("app.messaging.kafka.logger.info", side_effect=RuntimeError("log unavailable")):
        with pytest.raises(RuntimeError, match="log unavailable"):
            asyncio.run(
                log_ticket_created(
                    consumer,
                    _message(TicketCreated(ticket_id=uuid4())),
                    group_id="ticket-notifications",
                )
            )

    consumer.commit.assert_not_awaited()


@pytest.mark.parametrize("group_id", ["ticket-notifications", "ticket-metrics"])
def test_worker_subscribes_with_own_group_and_manual_commit(group_id: str) -> None:
    stop_event = asyncio.Event()
    consumer = Mock()
    consumer.start = AsyncMock()
    consumer.stop = AsyncMock()
    ticket = TicketCreated(ticket_id=uuid4())

    async def getmany(**_kwargs: object) -> dict[TopicPartition, list[SimpleNamespace]]:
        stop_event.set()
        return {TopicPartition("ticket.created", 0): [_message(ticket, partition=0, offset=3)]}

    consumer.getmany = AsyncMock(side_effect=getmany)
    consumer.commit = AsyncMock()
    settings = SimpleNamespace(
        ticket_created_topic="ticket.created",
        analysis_completed_topic="analysis.completed",
        kafka_bootstrap_servers="localhost:9092",
        redis_url="redis://localhost:6379/0",
        redis_notification_channel="ticket.notifications",
    )
    redis = Mock(aclose=AsyncMock())
    with (
        patch("app.kafka_worker.AIOKafkaConsumer", return_value=consumer) as factory,
        patch("app.kafka_worker.get_settings", return_value=settings),
        patch("app.kafka_worker.Redis.from_url", return_value=redis) as redis_factory,
    ):
        asyncio.run(run_worker(group_id, stop_event))

    factory.assert_called_once_with(
        "ticket.created",
        "analysis.completed",
        bootstrap_servers="localhost:9092",
        group_id=group_id,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    consumer.start.assert_awaited_once()
    consumer.commit.assert_awaited_once_with({TopicPartition("ticket.created", 0): 4})
    consumer.stop.assert_awaited_once()
    if group_id == "ticket-notifications":
        redis_factory.assert_called_once_with("redis://localhost:6379/0")
    else:
        redis_factory.assert_not_called()
