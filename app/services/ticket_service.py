"""Ticket application service."""

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import Ticket, TicketCategory, TicketPriority, TicketStatus
from app.repositories.ticket_repository import TicketRepository
from app.repositories.user_repository import UserRepository


class TicketService:
    """Coordinate ticket workflows and repository transactions."""

    def __init__(
        self,
        ticket_repository: TicketRepository,
        user_repository: UserRepository,
        session: AsyncSession,
    ) -> None:
        self._tickets = ticket_repository
        self._users = user_repository
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
        await self._ensure_user_exists(user_id)
        try:
            ticket = await self._tickets.create(
                user_id=user_id,
                title=title,
                description=description,
                category=category,
                priority=priority,
            )
            await self._session.commit()
            await self._session.refresh(ticket)
            return ticket
        except IntegrityError as error:
            await self._session.rollback()
            raise LookupError("User not found") from error

    async def get(self, ticket_id: UUID) -> Ticket:
        ticket = await self._tickets.get(ticket_id)
        if ticket is None:
            raise LookupError("Ticket not found")
        return ticket

    async def list(
        self,
        *,
        page: int,
        page_size: int,
        status: TicketStatus | None = None,
        category: TicketCategory | None = None,
        priority: TicketPriority | None = None,
        user_id: UUID | None = None,
    ) -> tuple[list[Ticket], int]:
        return await self._tickets.list(
            offset=(page - 1) * page_size,
            limit=page_size,
            status=status,
            category=category,
            priority=priority,
            user_id=user_id,
        )

    async def update(self, ticket_id: UUID, **changes: object) -> Ticket:
        ticket = await self._tickets.update(await self.get(ticket_id), **changes)
        await self._session.commit()
        await self._session.refresh(ticket)
        return ticket

    async def delete(self, ticket_id: UUID) -> None:
        await self._tickets.delete(await self.get(ticket_id))
        await self._session.commit()

    async def _ensure_user_exists(self, user_id: UUID) -> None:
        if await self._users.get(user_id) is None:
            raise LookupError("User not found")
