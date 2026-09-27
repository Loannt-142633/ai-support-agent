"""Track email delivery for approved suggested answers."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ticket_suggested_answers", sa.Column("recipient_email", sa.String(length=255))
    )
    op.add_column(
        "ticket_suggested_answers", sa.Column("send_started_at", sa.DateTime(timezone=True))
    )
    op.add_column("ticket_suggested_answers", sa.Column("sent_at", sa.DateTime(timezone=True)))
    op.add_column(
        "ticket_suggested_answers", sa.Column("send_failure_reason", sa.String(length=255))
    )
    op.drop_constraint(
        "ck_ticket_suggested_answers_review", "ticket_suggested_answers", type_="check"
    )
    op.drop_constraint(
        "ck_ticket_suggested_answers_status", "ticket_suggested_answers", type_="check"
    )
    op.create_check_constraint(
        "ck_ticket_suggested_answers_status",
        "ticket_suggested_answers",
        "status IN ('draft', 'approved', 'rejected', 'pending_send', 'sent', 'send_failed')",
    )
    op.create_check_constraint(
        "ck_ticket_suggested_answers_review",
        "ticket_suggested_answers",
        "(status = 'draft' AND reviewed_at IS NULL AND rejection_reason IS NULL) OR "
        "(status IN ('approved', 'pending_send', 'sent', 'send_failed') "
        "AND reviewed_at IS NOT NULL AND rejection_reason IS NULL) OR "
        "(status = 'rejected' AND reviewed_at IS NOT NULL AND rejection_reason IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_ticket_suggested_answers_delivery",
        "ticket_suggested_answers",
        "(status IN ('draft', 'approved', 'rejected') AND recipient_email IS NULL "
        "AND send_started_at IS NULL AND sent_at IS NULL AND send_failure_reason IS NULL) OR "
        "(status = 'pending_send' AND recipient_email IS NOT NULL "
        "AND send_started_at IS NOT NULL AND sent_at IS NULL AND send_failure_reason IS NULL) OR "
        "(status = 'sent' AND recipient_email IS NOT NULL AND send_started_at IS NOT NULL "
        "AND sent_at IS NOT NULL AND send_failure_reason IS NULL) OR "
        "(status = 'send_failed' AND recipient_email IS NOT NULL "
        "AND send_started_at IS NOT NULL AND sent_at IS NULL AND send_failure_reason IS NOT NULL)",
    )


def downgrade() -> None:
    for name in (
        "ck_ticket_suggested_answers_delivery",
        "ck_ticket_suggested_answers_review",
        "ck_ticket_suggested_answers_status",
    ):
        op.drop_constraint(name, "ticket_suggested_answers", type_="check")
    op.execute(
        "UPDATE ticket_suggested_answers SET status = 'approved' "
        "WHERE status IN ('pending_send', 'sent', 'send_failed')"
    )
    op.create_check_constraint(
        "ck_ticket_suggested_answers_status",
        "ticket_suggested_answers",
        "status IN ('draft', 'approved', 'rejected')",
    )
    op.create_check_constraint(
        "ck_ticket_suggested_answers_review",
        "ticket_suggested_answers",
        "(status = 'draft' AND reviewed_at IS NULL AND rejection_reason IS NULL) OR "
        "(status = 'approved' AND reviewed_at IS NOT NULL AND rejection_reason IS NULL) OR "
        "(status = 'rejected' AND reviewed_at IS NOT NULL AND rejection_reason IS NOT NULL)",
    )
    op.drop_column("ticket_suggested_answers", "send_failure_reason")
    op.drop_column("ticket_suggested_answers", "sent_at")
    op.drop_column("ticket_suggested_answers", "send_started_at")
    op.drop_column("ticket_suggested_answers", "recipient_email")
