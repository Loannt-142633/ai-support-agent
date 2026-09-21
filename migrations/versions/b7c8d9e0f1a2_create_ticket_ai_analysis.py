"""Create ticket AI analysis table."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7c8d9e0f1a2"
down_revision: str | None = "8f1c2d3e4a5b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create storage for future AI analysis results."""

    op.create_table(
        "ticket_ai_analysis",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column(
            "predicted_category",
            sa.Enum(
                "general",
                "billing",
                "technical",
                name="ticket_ai_predicted_category",
            ),
            nullable=False,
        ),
        sa.Column(
            "predicted_priority",
            sa.Enum(
                "low",
                "medium",
                "high",
                "urgent",
                name="ticket_ai_predicted_priority",
            ),
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("requires_human", sa.Boolean(), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ticket_ai_analysis_ticket_id"),
        "ticket_ai_analysis",
        ["ticket_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the ticket AI analysis table."""

    op.drop_index(
        op.f("ix_ticket_ai_analysis_ticket_id"), table_name="ticket_ai_analysis"
    )
    op.drop_table("ticket_ai_analysis")
