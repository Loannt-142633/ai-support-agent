"""Contract for enqueueing ticket analysis work."""

from typing import Protocol
from uuid import UUID


class TicketAnalysisPublisher(Protocol):
    """Publish an analysis job for a persisted ticket."""

    async def publish(self, ticket_id: UUID) -> None: ...
