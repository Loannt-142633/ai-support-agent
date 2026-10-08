"""Boundary for publishing a persisted ticket analysis completion."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class AnalysisCompleted:
    """Identity of an analysis that has been committed to storage."""

    ticket_id: UUID
    analysis_id: UUID


class AnalysisCompletedPublisher(Protocol):
    """Publish an event after its analysis record exists."""

    async def publish(self, event: AnalysisCompleted) -> None: ...
