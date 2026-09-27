"""Persistence operations for AI-generated ticket analysis."""

from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket_ai_analysis import TicketAIAnalysis
from app.schemas.ticket_ai_analysis import TicketAIAnalysisOutput


class TicketAIAnalysisRepository:
    """Read and write analysis records in a job-scoped transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def exists_for_ticket(self, ticket_id: UUID) -> bool:
        statement = (
            select(TicketAIAnalysis.id).where(TicketAIAnalysis.ticket_id == ticket_id).limit(1)
        )
        return await self._session.scalar(statement) is not None

    async def get_by_ticket_id(self, ticket_id: UUID) -> TicketAIAnalysis | None:
        """Return the most recent persisted analysis for a ticket."""

        statement = (
            select(TicketAIAnalysis)
            .where(TicketAIAnalysis.ticket_id == ticket_id)
            .order_by(TicketAIAnalysis.created_at.desc(), TicketAIAnalysis.id.desc())
            .limit(1)
        )
        return cast(TicketAIAnalysis | None, await self._session.scalar(statement))

    async def create(
        self,
        *,
        ticket_id: UUID,
        output: TicketAIAnalysisOutput,
        model: str,
        prompt_version: str,
    ) -> TicketAIAnalysis:
        analysis = TicketAIAnalysis(
            ticket_id=ticket_id,
            predicted_category=output.category,
            predicted_priority=output.priority,
            summary=output.summary,
            requires_human=output.requires_human,
            model=model,
            prompt_version=prompt_version,
            confidence=None,
        )
        self._session.add(analysis)
        await self._session.flush()
        return analysis
