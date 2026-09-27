"""Generate a reviewable support reply draft for an existing ticket."""

from uuid import UUID

from app.repositories.ticket_repository import TicketRepository
from app.services.rag_service import RAGService


class SuggestedAnswerService:
    """Use ticket context as a RAG question without saving or sending a reply."""

    def __init__(self, tickets: TicketRepository, rag: RAGService) -> None:
        self._tickets = tickets
        self._rag = rag

    async def generate(self, ticket_id: UUID) -> str:
        ticket = await self._tickets.get(ticket_id)
        if ticket is None:
            raise LookupError("Ticket not found")

        question = f"{ticket.title.strip()}\n\n{ticket.description.strip()}".strip()
        return await self._rag.answer(question)
