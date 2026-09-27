"""Standalone RabbitMQ worker for document ingestion jobs."""

import asyncio
import logging
import signal
from pathlib import Path
from types import FrameType

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from app.api.dependencies import (
    get_chunking_service,
    get_document_parser,
    get_embedding_client,
    get_embedding_service,
)
from app.core.config import get_settings
from app.db.session import SessionLocal, engine
from app.jobs.document_ingestion_handler import DocumentIngestionJobHandler
from app.messaging.rabbitmq import RabbitMQDocumentIngestionConsumer
from app.storage.local import LocalDocumentStorage

logger = logging.getLogger(__name__)


def create_consumer() -> RabbitMQDocumentIngestionConsumer:
    """Wire the job handler to the same configured adapters used by the API."""

    settings = get_settings()
    handler = DocumentIngestionJobHandler(
        SessionLocal,
        LocalDocumentStorage(Path(settings.document_storage_dir)),
        get_document_parser(),
        get_chunking_service(),
        get_embedding_service(get_embedding_client()),
    )
    return RabbitMQDocumentIngestionConsumer(handler)


async def run_worker(stop_event: asyncio.Event) -> None:
    """Cancel consumption and drain active jobs before closing dependencies."""

    settings = get_settings()
    in_flight: set[asyncio.Task[None]] = set()
    stopping = False

    async def process_message(message: AbstractIncomingMessage) -> None:
        if stopping:
            # It was delivered before cancel-ok but has not started processing.
            # Leave it unacknowledged so the broker requeues it on connection close.
            logger.info("Deferring ingestion message %s during shutdown", message.message_id)
            return
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("Document ingestion callback is not running in a task")
        # No await between the stopping check and registration: a handler
        # cannot start without being visible to the shutdown drain.
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
            queue = await channel.declare_queue(settings.document_ingestion_queue, durable=True)
            consumer_tag = await queue.consume(process_message, no_ack=False)
            logger.info("Consuming document ingestion jobs from %s", queue.name)
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
                                    "In-flight document ingestion callback failed during shutdown",
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
    """Start the worker as a separate process from FastAPI."""

    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run_until_stopped())


if __name__ == "__main__":
    main()
