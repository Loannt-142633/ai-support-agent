"""FastAPI dependency providers for application services."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.repositories.ticket_repository import TicketRepository
from app.repositories.user_repository import UserRepository
from app.services.ticket_service import TicketService
from app.services.user_service import UserService

DbSession = Annotated[AsyncSession, Depends(get_db)]


def get_user_service(session: DbSession) -> UserService:
    """Build a user service for the current request."""

    return UserService(UserRepository(session), session)


def get_ticket_service(session: DbSession) -> TicketService:
    """Build a ticket service for the current request."""

    return TicketService(TicketRepository(session), UserRepository(session), session)
