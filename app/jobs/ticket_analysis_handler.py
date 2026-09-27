"""Analyze one ticket and persist its AI result without depending on RabbitMQ."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.ticket_ai_analysis_repository import TicketAIAnalysisRepository
from app.repositories.ticket_repository import TicketRepository
from app.services.ticket_analysis_service import TicketAnalysisService


class TicketNotFoundError(LookupError):
    """Raised when an analysis job references a missing ticket."""

    def __init__(self, ticket_id: UUID) -> None:
        self.ticket_id = ticket_id
        super().__init__(f"Ticket {ticket_id} not found")


class TicketAnalysisJobHandler:
    """Use one session per delivery and skip jobs already persisted."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        analysis_service: TicketAnalysisService,
        *,
        model_name: str,
    ) -> None:
        self._session_factory = session_factory
        self._analysis_service = analysis_service
        self._model_name = model_name

    async def handle(self, ticket_id: UUID) -> None:
        async with self._session_factory() as session:
            ticket = await TicketRepository(session).get(ticket_id)
            if ticket is None:
                raise TicketNotFoundError(ticket_id)

            analyses = TicketAIAnalysisRepository(session)
            if await analyses.exists_for_ticket(ticket_id):
                return

            output = await self._analysis_service.analyze(ticket)
            await analyses.create(
                ticket_id=ticket_id,
                output=output,
                model=self._model_name,
                prompt_version=self._analysis_service.prompt_version,
            )
            await session.commit()
