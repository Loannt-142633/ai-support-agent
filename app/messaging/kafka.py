"""Kafka transports for ticket lifecycle events."""

import json
import logging
from uuid import UUID

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer  # type: ignore[import-untyped]
from aiokafka.structs import ConsumerRecord, TopicPartition  # type: ignore[import-untyped]

from app.services.analysis_completed_publisher import AnalysisCompleted
from app.services.ticket_created_publisher import TicketCreated

logger = logging.getLogger(__name__)


def encode_ticket_created(event: TicketCreated) -> bytes:
    """Serialize the versioned event as UTF-8 JSON."""

    return json.dumps(
        {
            "version": 1,
            "ticket_id": str(event.ticket_id),
        },
        separators=(",", ":"),
    ).encode("utf-8")


def decode_ticket_created(value: bytes, key: bytes | None) -> TicketCreated:
    """Read the published contract and verify its ticket ID matches the Kafka key."""

    try:
        payload = json.loads(value)
        if (
            not isinstance(payload, dict)
            or payload.get("version") != 1
            or not isinstance(payload.get("ticket_id"), str)
        ):
            raise ValueError("Invalid ticket.created event")
        ticket_id = UUID(payload["ticket_id"])
        if key != str(ticket_id).encode("utf-8"):
            raise ValueError("ticket_id does not match Kafka message key")
        return TicketCreated(ticket_id=ticket_id)
    except (UnicodeDecodeError, TypeError, ValueError) as error:
        raise ValueError("Invalid ticket.created event") from error


async def log_ticket_created(
    consumer: AIOKafkaConsumer, message: ConsumerRecord, *, group_id: str
) -> None:
    """Log one valid event, then commit exactly its next offset."""

    event = decode_ticket_created(message.value, message.key)
    logger.info(
        "ticket_id=%s partition=%s offset=%s group_id=%s",
        event.ticket_id,
        message.partition,
        message.offset,
        group_id,
    )
    await consumer.commit({TopicPartition(message.topic, message.partition): message.offset + 1})


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


def encode_analysis_completed(event: AnalysisCompleted) -> bytes:
    """Serialize the analysis identity as a versioned Kafka event."""

    return json.dumps(
        {
            "version": 1,
            "ticket_id": str(event.ticket_id),
            "analysis_id": str(event.analysis_id),
        },
        separators=(",", ":"),
    ).encode("utf-8")


def decode_analysis_completed(value: bytes, key: bytes | None) -> AnalysisCompleted:
    """Validate an analysis event and its ticket ID message key."""

    try:
        payload = json.loads(value)
        if (
            not isinstance(payload, dict)
            or payload.get("version") != 1
            or not isinstance(payload.get("ticket_id"), str)
            or not isinstance(payload.get("analysis_id"), str)
        ):
            raise ValueError("Invalid analysis.completed event")
        ticket_id = UUID(payload["ticket_id"])
        analysis_id = UUID(payload["analysis_id"])
        if key != str(ticket_id).encode("utf-8"):
            raise ValueError("ticket_id does not match Kafka message key")
        return AnalysisCompleted(ticket_id=ticket_id, analysis_id=analysis_id)
    except (UnicodeDecodeError, TypeError, ValueError) as error:
        raise ValueError("Invalid analysis.completed event") from error


async def log_analysis_completed(
    consumer: AIOKafkaConsumer, message: ConsumerRecord, *, group_id: str
) -> None:
    """Log a valid analysis completion and commit its next offset."""

    event = decode_analysis_completed(message.value, message.key)
    logger.info(
        "event=analysis.completed ticket_id=%s analysis_id=%s partition=%s offset=%s group_id=%s",
        event.ticket_id,
        event.analysis_id,
        message.partition,
        message.offset,
        group_id,
    )
    await consumer.commit({TopicPartition(message.topic, message.partition): message.offset + 1})


class KafkaAnalysisCompletedPublisher:
    """Publish analysis completion with ticket ID as the Kafka message key."""

    def __init__(self, *, bootstrap_servers: str, topic: str) -> None:
        if not bootstrap_servers.strip() or not topic.strip():
            raise ValueError("Kafka bootstrap servers and topic must be configured")
        self._bootstrap_servers = bootstrap_servers
        self._topic = topic

    async def publish(self, event: AnalysisCompleted) -> None:
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
                value=encode_analysis_completed(event),
            )
        finally:
            await producer.stop()
