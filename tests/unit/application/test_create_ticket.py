import asyncio
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from app.models.ticket import Ticket, TicketCategory, TicketPriority
from app.models.user import User
from app.repositories.ticket_repository import TicketRepository
from app.repositories.user_repository import UserRepository
from app.services.ticket_created_publisher import TicketCreated
from app.services.ticket_service import TicketService


def test_create_ticket_persists_ticket() -> None:
    ticket_repository = Mock(spec=TicketRepository)
    user_repository = Mock(spec=UserRepository)
    user_id = uuid4()
    ticket = Ticket(
        id=uuid4(),
        user_id=user_id,
        title="Cannot sign in",
        description="The reset link has expired.",
        category=TicketCategory.GENERAL,
        priority=TicketPriority.MEDIUM,
    )
    ticket_repository.create = AsyncMock(return_value=ticket)
    user_repository.get = AsyncMock(return_value=Mock(spec=User))
    session = Mock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    publisher = AsyncMock()
    events: list[str] = []

    async def commit() -> None:
        events.append("commit")

    async def refresh(_ticket: Ticket) -> None:
        events.append("refresh")

    async def publish(ticket_id: object) -> None:
        assert ticket_id == ticket.id
        events.append("analysis_publish")

    async def publish_created(event: TicketCreated) -> None:
        assert event.ticket_id == ticket.id
        events.append("created_publish")

    session.commit.side_effect = commit
    session.refresh.side_effect = refresh
    publisher.publish.side_effect = publish
    created_publisher = AsyncMock()
    created_publisher.publish.side_effect = publish_created
    service = TicketService(
        ticket_repository, user_repository, session, publisher, created_publisher
    )

    result = asyncio.run(
        service.create(
            user_id=user_id,
            title="Cannot sign in",
            description="The reset link has expired.",
            category=TicketCategory.GENERAL,
            priority=TicketPriority.MEDIUM,
        )
    )

    assert result is ticket
    ticket_repository.create.assert_called_once()
    publisher.publish.assert_awaited_once_with(ticket.id)
    event = created_publisher.publish.await_args.args[0]
    assert isinstance(event, TicketCreated)
    assert event.ticket_id == ticket.id
    assert events == ["commit", "created_publish", "analysis_publish", "refresh"]


@pytest.mark.parametrize("failure_point", ["user", "create", "commit"])
def test_create_ticket_failure_does_not_publish(failure_point: str) -> None:
    ticket_repository = Mock(spec=TicketRepository)
    ticket_repository.create = AsyncMock(return_value=Ticket(id=uuid4()))
    user_repository = Mock(spec=UserRepository)
    user_repository.get = AsyncMock(return_value=Mock(spec=User))
    session = Mock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    publisher = AsyncMock()
    created_publisher = AsyncMock()
    service = TicketService(
        ticket_repository, user_repository, session, publisher, created_publisher
    )

    if failure_point == "user":
        user_repository.get.return_value = None
        expected_error: type[Exception] = LookupError
    elif failure_point == "create":
        ticket_repository.create.side_effect = RuntimeError("insert failed")
        expected_error = RuntimeError
    else:
        session.commit.side_effect = RuntimeError("commit failed")
        expected_error = RuntimeError

    with pytest.raises(expected_error):
        asyncio.run(
            service.create(
                user_id=uuid4(),
                title="Cannot sign in",
                description="The reset link has expired.",
                category=TicketCategory.GENERAL,
                priority=TicketPriority.MEDIUM,
            )
        )

    publisher.publish.assert_not_awaited()
    created_publisher.publish.assert_not_awaited()
    if failure_point == "user":
        session.commit.assert_not_awaited()
    else:
        session.rollback.assert_awaited_once()


def test_publish_failure_does_not_roll_back_committed_ticket() -> None:
    ticket_repository = Mock(spec=TicketRepository)
    ticket = Ticket(id=uuid4())
    ticket_repository.create = AsyncMock(return_value=ticket)
    user_repository = Mock(spec=UserRepository)
    user_repository.get = AsyncMock(return_value=Mock(spec=User))
    session = Mock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    publisher = AsyncMock()
    publisher.publish.side_effect = RuntimeError("queue unavailable")
    created_publisher = AsyncMock()
    service = TicketService(
        ticket_repository, user_repository, session, publisher, created_publisher
    )

    with pytest.raises(RuntimeError, match="queue unavailable"):
        asyncio.run(
            service.create(
                user_id=uuid4(),
                title="Cannot sign in",
                description="The reset link has expired.",
                category=TicketCategory.GENERAL,
                priority=TicketPriority.MEDIUM,
            )
        )

    session.commit.assert_awaited_once()
    publisher.publish.assert_awaited_once_with(ticket.id)
    session.refresh.assert_not_awaited()
    session.rollback.assert_not_awaited()
    created_publisher.publish.assert_awaited_once_with(TicketCreated(ticket_id=ticket.id))


def test_kafka_publish_failure_does_not_publish_analysis() -> None:
    ticket = Ticket(id=uuid4())
    tickets = Mock(spec=TicketRepository)
    tickets.create = AsyncMock(return_value=ticket)
    users = Mock(spec=UserRepository)
    users.get = AsyncMock(return_value=Mock(spec=User))
    session = Mock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    analysis = AsyncMock()
    created = AsyncMock()
    created.publish.side_effect = RuntimeError("Kafka unavailable")
    service = TicketService(tickets, users, session, analysis, created)

    with pytest.raises(RuntimeError, match="Kafka unavailable"):
        asyncio.run(
            service.create(
                user_id=uuid4(),
                title="Cannot sign in",
                description="The reset link has expired.",
                category=TicketCategory.GENERAL,
                priority=TicketPriority.MEDIUM,
            )
        )

    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()
    created.publish.assert_awaited_once_with(TicketCreated(ticket_id=ticket.id))
    analysis.publish.assert_not_awaited()
