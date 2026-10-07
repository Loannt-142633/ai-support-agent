"""Boundary for publishing a ticket-created domain event."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class TicketCreated:
    """Stable facts captured when a ticket is first committed."""

    ticket_id: UUID


class TicketCreatedPublisher(Protocol):
    """Publish the same event to independent Kafka consumer groups."""

    async def publish(self, event: TicketCreated) -> None: ...
