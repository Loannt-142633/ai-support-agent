"""SQLAlchemy repository for tickets."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import Ticket, TicketCategory, TicketPriority, TicketStatus


class TicketRepository:
    """Persist and query tickets."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: UUID,
        title: str,
        description: str,
        category: TicketCategory,
        priority: TicketPriority,
    ) -> Ticket:
        ticket = Ticket(
            user_id=user_id,
            title=title,
            description=description,
            category=category,
            priority=priority,
            status=TicketStatus.OPEN,
        )
        self._session.add(ticket)
        await self._session.flush()
        return ticket

    async def get(self, ticket_id: UUID) -> Ticket | None:
        return await self._session.get(Ticket, ticket_id)

    async def list(
        self,
        *,
        offset: int,
        limit: int,
        status: TicketStatus | None = None,
        category: TicketCategory | None = None,
        priority: TicketPriority | None = None,
        user_id: UUID | None = None,
    ) -> tuple[list[Ticket], int]:
        statement = select(Ticket).order_by(Ticket.created_at.desc()).offset(offset).limit(limit)
        count_statement = select(func.count()).select_from(Ticket)
        if status is not None:
            statement = statement.where(Ticket.status == status)
            count_statement = count_statement.where(Ticket.status == status)
        if category is not None:
            statement = statement.where(Ticket.category == category)
            count_statement = count_statement.where(Ticket.category == category)
        if priority is not None:
            statement = statement.where(Ticket.priority == priority)
            count_statement = count_statement.where(Ticket.priority == priority)
        if user_id is not None:
            statement = statement.where(Ticket.user_id == user_id)
            count_statement = count_statement.where(Ticket.user_id == user_id)
        result = await self._session.scalars(statement)
        total = await self._session.scalar(count_statement)
        return list(result), total or 0

    async def update(self, ticket: Ticket, **changes: object) -> Ticket:
        for field, value in changes.items():
            setattr(ticket, field, value)
        await self._session.flush()
        return ticket

    async def delete(self, ticket: Ticket) -> None:
        await self._session.delete(ticket)
        await self._session.flush()
