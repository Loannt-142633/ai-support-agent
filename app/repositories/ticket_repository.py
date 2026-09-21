"""SQLAlchemy repository for tickets."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ticket import Ticket, TicketCategory, TicketPriority, TicketStatus


class TicketRepository:
    """Persist and query tickets."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
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
        self._session.flush()
        return ticket

    def get(self, ticket_id: UUID) -> Ticket | None:
        return self._session.get(Ticket, ticket_id)

    def list(
        self,
        *,
        status: TicketStatus | None = None,
        category: TicketCategory | None = None,
        priority: TicketPriority | None = None,
        user_id: UUID | None = None,
    ) -> list[Ticket]:
        statement = select(Ticket).order_by(Ticket.created_at.desc())
        if status is not None:
            statement = statement.where(Ticket.status == status)
        if category is not None:
            statement = statement.where(Ticket.category == category)
        if priority is not None:
            statement = statement.where(Ticket.priority == priority)
        if user_id is not None:
            statement = statement.where(Ticket.user_id == user_id)
        return list(self._session.scalars(statement))

    def update(self, ticket: Ticket, **changes: object) -> Ticket:
        for field, value in changes.items():
            setattr(ticket, field, value)
        self._session.flush()
        return ticket

    def delete(self, ticket: Ticket) -> None:
        self._session.delete(ticket)
        self._session.flush()
