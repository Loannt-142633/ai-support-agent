"""Allow a suggested answer to be edited and decided once."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ticket_suggested_answers", sa.Column("staff_content", sa.Text()))
    op.add_column(
        "ticket_suggested_answers", sa.Column("updated_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "ticket_suggested_answers", sa.Column("reviewed_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "ticket_suggested_answers", sa.Column("rejection_reason", sa.String(length=500))
    )
    op.drop_constraint(
        "ck_ticket_suggested_answers_status", "ticket_suggested_answers", type_="check"
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


def downgrade() -> None:
    op.drop_constraint(
        "ck_ticket_suggested_answers_review", "ticket_suggested_answers", type_="check"
    )
    op.drop_constraint(
        "ck_ticket_suggested_answers_status", "ticket_suggested_answers", type_="check"
    )
    op.execute("UPDATE ticket_suggested_answers SET status = 'draft'")
    op.create_check_constraint(
        "ck_ticket_suggested_answers_status", "ticket_suggested_answers", "status = 'draft'"
    )
    op.drop_column("ticket_suggested_answers", "rejection_reason")
    op.drop_column("ticket_suggested_answers", "reviewed_at")
    op.drop_column("ticket_suggested_answers", "updated_at")
    op.drop_column("ticket_suggested_answers", "staff_content")
