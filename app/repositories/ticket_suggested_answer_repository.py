"""Persistence operations for reviewable AI answer drafts."""

from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.ticket_suggested_answer import TicketSuggestedAnswer, TicketSuggestedAnswerSource
from app.repositories.document_chunk_repository import SimilarDocumentChunk


class TicketSuggestedAnswerRepository:
    """Save drafts and retrieve them by both ticket and draft identity."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, ticket_id: UUID, ai_content: str, chunks: tuple[SimilarDocumentChunk, ...]
    ) -> TicketSuggestedAnswer:
        draft = TicketSuggestedAnswer(ticket_id=ticket_id, ai_content=ai_content)
        draft.sources = [
            TicketSuggestedAnswerSource(
                position=position,
                document_id=chunk.document_id,
                chunk_index=chunk.chunk_index,
            )
            for position, chunk in enumerate(chunks)
        ]
        self._session.add(draft)
        await self._session.flush()
        return draft

    async def get_for_ticket(
        self, *, ticket_id: UUID, draft_id: UUID
    ) -> TicketSuggestedAnswer | None:
        statement = (
            select(TicketSuggestedAnswer)
            .options(selectinload(TicketSuggestedAnswer.sources))
            .where(
                TicketSuggestedAnswer.id == draft_id,
                TicketSuggestedAnswer.ticket_id == ticket_id,
            )
        )
        return cast(TicketSuggestedAnswer | None, await self._session.scalar(statement))

    async def get_for_ticket_for_update(
        self, *, ticket_id: UUID, draft_id: UUID
    ) -> TicketSuggestedAnswer | None:
        """Lock the draft until the edit/review transaction commits."""

        statement = (
            select(TicketSuggestedAnswer)
            .options(selectinload(TicketSuggestedAnswer.sources))
            .where(
                TicketSuggestedAnswer.id == draft_id,
                TicketSuggestedAnswer.ticket_id == ticket_id,
            )
            .with_for_update(of=TicketSuggestedAnswer)
        )
        return cast(TicketSuggestedAnswer | None, await self._session.scalar(statement))
