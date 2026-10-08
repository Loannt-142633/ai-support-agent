"""Run Kafka ticket event consumers for notifications and metrics."""

import argparse
import asyncio
import logging
import signal
from types import FrameType
from typing import Literal, cast

from aiokafka import AIOKafkaConsumer  # type: ignore[import-untyped]
from aiokafka.structs import TopicPartition  # type: ignore[import-untyped]
from redis.asyncio import Redis

from app.core.config import get_settings
from app.messaging.kafka import (
    decode_analysis_completed,
    log_analysis_completed,
    log_ticket_created,
)
from app.messaging.redis import RedisAnalysisNotificationPublisher

logger = logging.getLogger(__name__)
GroupId = Literal["ticket-notifications", "ticket-metrics"]


async def run_worker(group_id: GroupId, stop_event: asyncio.Event) -> None:
    """Read one record at a time; leave failed records uncommitted for replay."""

    settings = get_settings()
    consumer = AIOKafkaConsumer(
        settings.ticket_created_topic,
        settings.analysis_completed_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=group_id,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    redis = Redis.from_url(settings.redis_url) if group_id == "ticket-notifications" else None
    await consumer.start()
    logger.info(
        "Subscribed to %s, %s with group_id=%s",
        settings.ticket_created_topic,
        settings.analysis_completed_topic,
        group_id,
    )
    try:
        while not stop_event.is_set():
            batches = await consumer.getmany(timeout_ms=1000, max_records=1)
            for messages in batches.values():
                for message in messages:
                    try:
                        if message.topic == settings.ticket_created_topic:
                            await log_ticket_created(consumer, message, group_id=group_id)
                        elif message.topic == settings.analysis_completed_topic:
                            if redis is None:
                                await log_analysis_completed(consumer, message, group_id=group_id)
                            else:
                                event = decode_analysis_completed(message.value, message.key)
                                publisher = RedisAnalysisNotificationPublisher(
                                    redis, channel=settings.redis_notification_channel
                                )
                                await publisher.publish(event)
                                logger.info(
                                    "event=analysis.completed ticket_id=%s analysis_id=%s "
                                    "partition=%s offset=%s group_id=%s",
                                    event.ticket_id,
                                    event.analysis_id,
                                    message.partition,
                                    message.offset,
                                    group_id,
                                )
                                await consumer.commit(
                                    {
                                        TopicPartition(message.topic, message.partition):
                                        message.offset + 1
                                    }
                                )
                        else:
                            raise ValueError(f"Unexpected Kafka topic: {message.topic}")
                    except Exception:
                        logger.exception(
                            "Failed to process partition=%s offset=%s group_id=%s; "
                            "offset remains uncommitted",
                            message.partition,
                            message.offset,
                            group_id,
                        )
                        raise
    finally:
        await consumer.stop()
        if redis is not None:
            await redis.aclose()


async def _run_until_stopped(group_id: GroupId) -> None:
    """Translate process termination into a graceful Kafka disconnect."""

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        loop.call_soon_threadsafe(stop_event.set)

    signals = (signal.SIGINT, signal.SIGTERM)
    previous_handlers = {sig: signal.getsignal(sig) for sig in signals}
    try:
        for sig in signals:
            signal.signal(sig, request_stop)
        await run_worker(group_id, stop_event)
    finally:
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)


def main() -> None:
    """Start one of the two independent Kafka consumer groups."""

    parser = argparse.ArgumentParser(description="Process ticket.created and analysis.completed")
    parser.add_argument("group_id", choices=("ticket-notifications", "ticket-metrics"))
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run_until_stopped(cast(GroupId, arguments.group_id)))


if __name__ == "__main__":
    main()
