"""Run independent Kafka ticket-created logging consumers."""

import argparse
import asyncio
import logging
import signal
from types import FrameType
from typing import Literal, cast

from aiokafka import AIOKafkaConsumer  # type: ignore[import-untyped]

from app.core.config import get_settings
from app.messaging.kafka import log_ticket_created

logger = logging.getLogger(__name__)
GroupId = Literal["ticket-notifications", "ticket-metrics"]


async def run_worker(group_id: GroupId, stop_event: asyncio.Event) -> None:
    """Read one record at a time; leave failed records uncommitted for replay."""

    settings = get_settings()
    consumer = AIOKafkaConsumer(
        settings.ticket_created_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=group_id,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    logger.info("Subscribed to %s with group_id=%s", settings.ticket_created_topic, group_id)
    try:
        while not stop_event.is_set():
            batches = await consumer.getmany(timeout_ms=1000, max_records=1)
            for messages in batches.values():
                for message in messages:
                    try:
                        await log_ticket_created(consumer, message, group_id=group_id)
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

    parser = argparse.ArgumentParser(description="Log ticket.created Kafka events")
    parser.add_argument("group_id", choices=("ticket-notifications", "ticket-metrics"))
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run_until_stopped(cast(GroupId, arguments.group_id)))


if __name__ == "__main__":
    main()
