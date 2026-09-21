from app.models.ticket import Ticket, TicketStatus


def test_ticket_has_expected_fields() -> None:
    ticket = Ticket(
        user_id="00000000-0000-0000-0000-000000000001",
        title="Cannot sign in",
        description="The reset link has expired.",
        status=TicketStatus.OPEN,
    )

    assert ticket.status is TicketStatus.OPEN
    assert ticket.title == "Cannot sign in"
    assert ticket.description == "The reset link has expired."
