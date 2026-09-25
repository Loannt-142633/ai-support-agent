"""Contract for enqueueing document ingestion work."""

from typing import Protocol
from uuid import UUID


class DocumentIngestionPublisher(Protocol):
    """Publish an ingestion job for a persisted document."""

    async def publish(self, document_id: UUID) -> None: ...
