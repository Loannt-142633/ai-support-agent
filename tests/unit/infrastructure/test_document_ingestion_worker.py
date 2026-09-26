import asyncio
import signal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.worker import _run_until_stopped, create_consumer, run_worker


def test_create_consumer_wires_job_handler_with_configured_dependencies() -> None:
    settings = SimpleNamespace(document_storage_dir="uploads/documents")

    with (
        patch("app.worker.get_settings", return_value=settings),
        patch("app.worker.SessionLocal") as sessions,
        patch("app.worker.LocalDocumentStorage") as storage,
        patch("app.worker.get_document_parser") as parser,
        patch("app.worker.get_chunking_service") as chunking,
        patch("app.worker.get_embedding_client") as embedding_client,
        patch("app.worker.get_embedding_service") as embedding_service,
        patch("app.worker.DocumentIngestionJobHandler") as handler,
        patch("app.worker.RabbitMQDocumentIngestionConsumer") as consumer,
    ):
        result = create_consumer()

    storage.assert_called_once_with(Path("uploads/documents"))
    embedding_service.assert_called_once_with(embedding_client.return_value)
    handler.assert_called_once_with(
        sessions,
        storage.return_value,
        parser.return_value,
        chunking.return_value,
        embedding_service.return_value,
    )
    consumer.assert_called_once_with(handler.return_value)
    assert result is consumer.return_value


def test_worker_subscribes_until_stopped_then_closes_connection_and_db_engine() -> None:
    settings = SimpleNamespace(
        rabbitmq_url="amqp://app:app@localhost:5672/",
        document_ingestion_queue="document.ingestion",
    )
    connection = AsyncMock()
    connection.__aenter__.return_value = connection
    channel = AsyncMock()
    connection.channel.return_value = channel
    queue = AsyncMock()
    queue.name = "document.ingestion"
    channel.declare_queue.return_value = queue
    consumer = MagicMock()
    consumer.process_message = AsyncMock()
    fake_engine = SimpleNamespace(dispose=AsyncMock())

    async def scenario() -> None:
        stop_event = asyncio.Event()
        subscribed = asyncio.Event()

        async def subscribe(*_args: object, **_kwargs: object) -> str:
            subscribed.set()
            return "consumer-tag"

        queue.consume.side_effect = subscribe

        with (
            patch("app.worker.get_settings", return_value=settings),
            patch("app.worker.create_consumer", return_value=consumer),
            patch("app.worker.aio_pika.connect_robust", new_callable=AsyncMock) as connect,
            patch("app.worker.engine", new=fake_engine),
        ):
            connect.return_value = connection
            task = asyncio.create_task(run_worker(stop_event))
            await asyncio.wait_for(subscribed.wait(), timeout=1)
            assert not task.done()
            stop_event.set()
            await task

        connect.assert_awaited_once_with(settings.rabbitmq_url, timeout=5)
        connection.channel.assert_awaited_once_with()
        channel.declare_queue.assert_awaited_once_with(
            settings.document_ingestion_queue, durable=True
        )
        queue.consume.assert_awaited_once_with(consumer.process_message, no_ack=False)
        connection.__aexit__.assert_awaited_once()
        fake_engine.dispose.assert_awaited_once_with()

    asyncio.run(scenario())


def test_worker_closes_connection_and_db_engine_when_subscription_fails() -> None:
    settings = SimpleNamespace(
        rabbitmq_url="amqp://app:app@localhost:5672/",
        document_ingestion_queue="document.ingestion",
    )
    connection = AsyncMock()
    connection.__aenter__.return_value = connection
    channel = AsyncMock()
    connection.channel.return_value = channel
    channel.declare_queue.side_effect = RuntimeError("queue unavailable")
    fake_engine = SimpleNamespace(dispose=AsyncMock())

    with (
        patch("app.worker.get_settings", return_value=settings),
        patch("app.worker.create_consumer", return_value=MagicMock()),
        patch("app.worker.aio_pika.connect_robust", new_callable=AsyncMock) as connect,
        patch("app.worker.engine", new=fake_engine),
    ):
        connect.return_value = connection
        with pytest.raises(RuntimeError, match="queue unavailable"):
            asyncio.run(run_worker(asyncio.Event()))

    connection.__aexit__.assert_awaited_once()
    fake_engine.dispose.assert_awaited_once_with()


def test_entrypoint_turns_sigterm_into_worker_stop() -> None:
    handlers: dict[signal.Signals, object] = {}

    def register(sig: signal.Signals, handler: object) -> None:
        handlers[sig] = handler

    async def verify_stop(stop_event: asyncio.Event) -> None:
        assert signal.SIGINT in handlers
        assert signal.SIGTERM in handlers
        stop_handler = handlers[signal.SIGTERM]
        assert callable(stop_handler)
        stop_handler(signal.SIGTERM, None)
        await asyncio.wait_for(stop_event.wait(), timeout=1)

    with (
        patch("app.worker.signal.getsignal", return_value=signal.SIG_DFL),
        patch("app.worker.signal.signal", side_effect=register) as install,
        patch("app.worker.run_worker", side_effect=verify_stop) as worker,
    ):
        asyncio.run(_run_until_stopped())

    worker.assert_awaited_once()
    assert install.call_count == 4
    assert handlers[signal.SIGINT] == signal.SIG_DFL
    assert handlers[signal.SIGTERM] == signal.SIG_DFL
