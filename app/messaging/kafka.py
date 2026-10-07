"""Kafka transport for ticket-created events."""

import json

from aiokafka import AIOKafkaProducer  # type: ignore[import-untyped]

from app.services.ticket_created_publisher import TicketCreated


def encode_ticket_created(event: TicketCreated) -> bytes:
    """Serialize the versioned event as UTF-8 JSON."""

    return json.dumps(
        {
            "version": 1,
            "ticket_id": str(event.ticket_id),
        },
        separators=(",", ":"),
    ).encode("utf-8")


class KafkaTicketCreatedPublisher:
    """Publish with Kafka broker acknowledgement and ticket ID as message key."""

    def __init__(self, *, bootstrap_servers: str, topic: str) -> None:
        if not bootstrap_servers.strip() or not topic.strip():
            raise ValueError("Kafka bootstrap servers and topic must be configured")
        self._bootstrap_servers = bootstrap_servers
        self._topic = topic

    async def publish(self, event: TicketCreated) -> None:
        producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            acks="all",
            enable_idempotence=True,
        )
        await producer.start()
        try:
            await producer.send_and_wait(
                self._topic,
                key=str(event.ticket_id).encode("utf-8"),
                value=encode_ticket_created(event),
            )
        finally:
            await producer.stop()
