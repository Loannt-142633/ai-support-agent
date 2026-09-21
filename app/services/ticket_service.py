"""Ticket application service."""

from uuid import UUID

from app.models.ticket import Ticket, TicketCategory, TicketPriority, TicketStatus
from app.repositories.ticket_repository import TicketRepository
from app.repositories.user_repository import UserRepository


class TicketService:
    """Coordinate ticket workflows and repository transactions."""

    def __init__(
        self, ticket_repository: TicketRepository, user_repository: UserRepository
    ) -> None:
        self._tickets = ticket_repository
        self._users = user_repository

    def create(
        self,
        *,
        user_id: UUID,
        title: str,
        description: str,
        category: TicketCategory,
        priority: TicketPriority,
    ) -> Ticket:
        self._ensure_user_exists(user_id)
        return self._tickets.create(
            user_id=user_id,
            title=title,
            description=description,
            category=category,
            priority=priority,
        )

    def get(self, ticket_id: UUID) -> Ticket:
        ticket = self._tickets.get(ticket_id)
        if ticket is None:
            raise LookupError("Ticket not found")
        return ticket

    def list(
        self,
        *,
        status: TicketStatus | None = None,
        category: TicketCategory | None = None,
        priority: TicketPriority | None = None,
        user_id: UUID | None = None,
    ) -> list[Ticket]:
        return self._tickets.list(
            status=status, category=category, priority=priority, user_id=user_id
        )

    def update(self, ticket_id: UUID, **changes: object) -> Ticket:
        return self._tickets.update(self.get(ticket_id), **changes)

    def delete(self, ticket_id: UUID) -> None:
        self._tickets.delete(self.get(ticket_id))

    def _ensure_user_exists(self, user_id: UUID) -> None:
        if self._users.get(user_id) is None:
            raise LookupError("User not found")
