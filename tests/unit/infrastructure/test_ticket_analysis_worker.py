"""Worker wiring and safe shutdown for ticket analysis deliveries."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.ticket_worker import create_consumer, run_worker


def test_create_consumer_wires_llm_and_job_handler() -> None:
    settings = SimpleNamespace(gemini_model="test-gemini")
    with (
        patch("app.ticket_worker.get_settings", return_value=settings),
        patch("app.ticket_worker.SessionLocal") as sessions,
        patch("app.ticket_worker.get_llm_client") as llm,
        patch("app.ticket_worker.get_ticket_analysis_service") as analysis,
        patch("app.ticket_worker.TicketAnalysisJobHandler") as handler,
        patch("app.ticket_worker.RabbitMQTicketAnalysisConsumer") as consumer,
    ):
        result = create_consumer()

    analysis.assert_called_once_with(llm.return_value)
    handler.assert_called_once_with(sessions, analysis.return_value, model_name="test-gemini")
    consumer.assert_called_once_with(handler.return_value)
    assert result is consumer.return_value


def test_worker_drains_active_job_before_closing_connection_and_engine() -> None:
    settings = SimpleNamespace(
        rabbitmq_url="amqp://app:app@localhost:5672/",
        ticket_analysis_queue="ticket.analysis",
    )
    connection = AsyncMock()
    connection.__aenter__.return_value = connection
    channel = AsyncMock()
    connection.channel.return_value = channel
    queue = AsyncMock()
    queue.name = "ticket.analysis"
    channel.declare_queue.return_value = queue
    fake_engine = SimpleNamespace(dispose=AsyncMock())
    consumer = MagicMock()
    message = SimpleNamespace(message_id="delivery-1")

    async def scenario() -> None:
        stop_event = asyncio.Event()
        subscribed = asyncio.Event()
        started = asyncio.Event()
        cancelled = asyncio.Event()
        release = asyncio.Event()

        async def subscribe(*_args: object, **_kwargs: object) -> str:
            channel.set_qos.assert_awaited_once_with(prefetch_count=1)
            subscribed.set()
            return "consumer-tag"

        async def process_message(_message: object) -> None:
            started.set()
            await release.wait()

        async def cancel(_tag: str) -> None:
            cancelled.set()

        queue.consume.side_effect = subscribe
        queue.cancel.side_effect = cancel
        consumer.process_message = AsyncMock(side_effect=process_message)

        with (
            patch("app.ticket_worker.get_settings", return_value=settings),
            patch("app.ticket_worker.create_consumer", return_value=consumer),
            patch("app.ticket_worker.aio_pika.connect_robust", new_callable=AsyncMock) as connect,
            patch("app.ticket_worker.engine", new=fake_engine),
        ):
            connect.return_value = connection
            worker_task = asyncio.create_task(run_worker(stop_event))
            await asyncio.wait_for(subscribed.wait(), timeout=1)
            callback = queue.consume.await_args.args[0]
            callback_task = asyncio.create_task(callback(message))
            await asyncio.wait_for(started.wait(), timeout=1)

            stop_event.set()
            await asyncio.wait_for(cancelled.wait(), timeout=1)
            assert not worker_task.done()
            connection.__aexit__.assert_not_awaited()
            fake_engine.dispose.assert_not_awaited()
            release.set()
            await asyncio.wait_for(callback_task, timeout=1)
            await asyncio.wait_for(worker_task, timeout=1)

        connect.assert_awaited_once_with(settings.rabbitmq_url, timeout=5)
        channel.declare_queue.assert_awaited_once_with(settings.ticket_analysis_queue, durable=True)
        queue.cancel.assert_awaited_once_with("consumer-tag")
        consumer.process_message.assert_awaited_once_with(message)
        connection.__aexit__.assert_awaited_once()
        fake_engine.dispose.assert_awaited_once()

    asyncio.run(scenario())
