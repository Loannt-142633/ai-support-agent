"""Generate and persist reviewable support reply drafts."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket_suggested_answer import TicketSuggestedAnswer
from app.repositories.ticket_repository import TicketRepository
from app.repositories.ticket_suggested_answer_repository import TicketSuggestedAnswerRepository
from app.services.rag_service import RAGService


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
