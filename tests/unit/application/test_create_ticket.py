from unittest.mock import Mock
from uuid import uuid4

from app.models.ticket import Ticket, TicketCategory, TicketPriority
from app.models.user import User
from app.repositories.ticket_repository import TicketRepository
from app.repositories.user_repository import UserRepository
from app.services.ticket_service import TicketService


def test_create_ticket_persists_ticket() -> None:
    ticket_repository = Mock(spec=TicketRepository)
    user_repository = Mock(spec=UserRepository)
    user_id = uuid4()
    ticket = Ticket(
        user_id=user_id,
        title="Cannot sign in",
        description="The reset link has expired.",
        category=TicketCategory.GENERAL,
        priority=TicketPriority.MEDIUM,
    )
    ticket_repository.create.return_value = ticket
    user_repository.get.return_value = Mock(spec=User)
    service = TicketService(ticket_repository, user_repository)

    result = service.create(
        user_id=user_id,
        title="Cannot sign in",
        description="The reset link has expired.",
        category=TicketCategory.GENERAL,
        priority=TicketPriority.MEDIUM,
    )

    assert result is ticket
    ticket_repository.create.assert_called_once()
