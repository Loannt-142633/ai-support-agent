"""Analyze one ticket and persist its AI result without depending on RabbitMQ."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.ticket_ai_analysis_repository import TicketAIAnalysisRepository
from app.repositories.ticket_repository import TicketRepository
from app.services.analysis_completed_publisher import AnalysisCompleted
from app.services.ticket_analysis_service import TicketAnalysisService


class TicketNotFoundError(LookupError):
    """Raised when an analysis job references a missing ticket."""

    def __init__(self, ticket_id: UUID) -> None:
        self.ticket_id = ticket_id
        super().__init__(f"Ticket {ticket_id} not found")


class TicketAnalysisJobHandler:
    """Persist one analysis and return its stable identity on redelivery."""

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

    async def handle(self, ticket_id: UUID) -> AnalysisCompleted:
        async with self._session_factory() as session:
            ticket = await TicketRepository(session).get(ticket_id)
            if ticket is None:
                raise TicketNotFoundError(ticket_id)

            analyses = TicketAIAnalysisRepository(session)
            existing = await analyses.get_by_ticket_id(ticket_id)
            if existing is not None:
                return AnalysisCompleted(ticket_id=ticket_id, analysis_id=existing.id)

            output = await self._analysis_service.analyze(ticket)
            analysis = await analyses.create(
                ticket_id=ticket_id,
                output=output,
                model=self._model_name,
                prompt_version=self._analysis_service.prompt_version,
            )
            await session.commit()
            return AnalysisCompleted(ticket_id=ticket_id, analysis_id=analysis.id)
