"""Generate and persist reviewable support reply drafts."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket_suggested_answer import TicketSuggestedAnswer
from app.repositories.ticket_repository import TicketRepository
from app.repositories.ticket_suggested_answer_repository import TicketSuggestedAnswerRepository
from app.services.rag_service import RAGService


class SuggestedAnswerAlreadyReviewedError(Exception):
    """The draft has a final review decision and cannot be changed again."""


class SuggestedAnswerService:
    """Use ticket context as a RAG question and save an unsent draft."""

    def __init__(
        self,
        tickets: TicketRepository,
        rag: RAGService,
        drafts: TicketSuggestedAnswerRepository,
        session: AsyncSession,
    ) -> None:
        self._tickets = tickets
        self._rag = rag
        self._drafts = drafts
        self._session = session

    async def generate(self, ticket_id: UUID) -> TicketSuggestedAnswer:
        ticket = await self._tickets.get(ticket_id)
        if ticket is None:
            raise LookupError("Ticket not found")

        question = f"{ticket.title.strip()}\n\n{ticket.description.strip()}".strip()
        result = await self._rag.answer(question)
        try:
            draft = await self._drafts.create(
                ticket_id=ticket_id, ai_content=result.answer, chunks=result.chunks
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return draft

    async def get(self, ticket_id: UUID, draft_id: UUID) -> TicketSuggestedAnswer:
        draft = await self._drafts.get_for_ticket(ticket_id=ticket_id, draft_id=draft_id)
        if draft is None:
            raise LookupError("Suggested answer not found")
        return draft

    async def edit(
        self, ticket_id: UUID, draft_id: UUID, staff_content: str
    ) -> TicketSuggestedAnswer:
        content = staff_content.strip()
        if not content:
            raise ValueError("staff_content must not be blank")
        try:
            draft = await self._open_draft_for_update(ticket_id, draft_id)
            draft.staff_content = content
            draft.updated_at = datetime.now(UTC)
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return draft

    async def approve(self, ticket_id: UUID, draft_id: UUID) -> TicketSuggestedAnswer:
        try:
            draft = await self._open_draft_for_update(ticket_id, draft_id)
            now = datetime.now(UTC)
            draft.status = "approved"
            draft.reviewed_at = now
            draft.updated_at = now
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return draft

    async def reject(
        self, ticket_id: UUID, draft_id: UUID, reason: str
    ) -> TicketSuggestedAnswer:
        normalized_reason = reason.strip()
        if not normalized_reason or len(normalized_reason) > 500:
            raise ValueError("reason must be between 1 and 500 characters")
        try:
            draft = await self._open_draft_for_update(ticket_id, draft_id)
            now = datetime.now(UTC)
            draft.status = "rejected"
            draft.rejection_reason = normalized_reason
            draft.reviewed_at = now
            draft.updated_at = now
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return draft

    async def _open_draft_for_update(
        self, ticket_id: UUID, draft_id: UUID
    ) -> TicketSuggestedAnswer:
        draft = await self._drafts.get_for_ticket_for_update(
            ticket_id=ticket_id, draft_id=draft_id
        )
        if draft is None:
            raise LookupError("Suggested answer not found")
        if draft.status != "draft":
            raise SuggestedAnswerAlreadyReviewedError(
                "Suggested answer has already been approved or rejected"
            )
        return draft
