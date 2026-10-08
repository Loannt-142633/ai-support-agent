"""Standalone RabbitMQ worker for ticket analysis jobs."""

import asyncio
import logging
import signal
from types import FrameType

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from app.api.dependencies import get_llm_client, get_ticket_analysis_service
from app.core.config import get_settings
from app.db.session import SessionLocal, engine
from app.jobs.ticket_analysis_handler import TicketAnalysisJobHandler
from app.messaging.kafka import KafkaAnalysisCompletedPublisher
from app.messaging.rabbitmq import RabbitMQTicketAnalysisConsumer

logger = logging.getLogger(__name__)


def create_consumer() -> RabbitMQTicketAnalysisConsumer:
    """Build the handler with the API's configured LLM adapter."""

    settings = get_settings()
    handler = TicketAnalysisJobHandler(
        SessionLocal,
        get_ticket_analysis_service(get_llm_client()),
        model_name=settings.gemini_model,
    )
    publisher = KafkaAnalysisCompletedPublisher(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        topic=settings.analysis_completed_topic,
    )
    return RabbitMQTicketAnalysisConsumer(handler, publisher)


async def run_worker(stop_event: asyncio.Event) -> None:
    """Stop receiving jobs, drain active callbacks, then close dependencies."""

    settings = get_settings()
    in_flight: set[asyncio.Task[None]] = set()
    stopping = False

    async def process_message(message: AbstractIncomingMessage) -> None:
        if stopping:
            logger.info("Deferring ticket analysis message %s during shutdown", message.message_id)
            return
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("Ticket analysis callback is not running in a task")
        in_flight.add(task)
        try:
            await consumer.process_message(message)
        finally:
            in_flight.discard(task)

    try:
        consumer = create_consumer()
        connection = await aio_pika.connect_robust(settings.rabbitmq_url, timeout=5)
        async with connection:
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=1)
            queue = await channel.declare_queue(settings.ticket_analysis_queue, durable=True)
            consumer_tag = await queue.consume(process_message, no_ack=False)
            logger.info("Consuming ticket analysis jobs from %s", queue.name)
            try:
                await stop_event.wait()
            finally:
                stopping = True
                try:
                    await queue.cancel(consumer_tag)
                finally:
                    while in_flight:
                        results = await asyncio.gather(*tuple(in_flight), return_exceptions=True)
                        for result in results:
                            if isinstance(result, BaseException):
                                logger.error(
                                    "In-flight ticket analysis callback failed during shutdown",
                                    exc_info=(type(result), result, result.__traceback__),
                                )
    finally:
        await engine.dispose()


async def _run_until_stopped() -> None:
    """Translate SIGINT/SIGTERM into a cooperative worker shutdown."""

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        loop.call_soon_threadsafe(stop_event.set)

    signals = (signal.SIGINT, signal.SIGTERM)
    previous_handlers = {sig: signal.getsignal(sig) for sig in signals}
    try:
        for sig in signals:
            signal.signal(sig, request_stop)
        await run_worker(stop_event)
    finally:
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run_until_stopped())


if __name__ == "__main__":
    main()
