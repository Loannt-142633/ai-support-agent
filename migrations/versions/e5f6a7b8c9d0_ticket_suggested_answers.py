"""Save support reply drafts and the document chunks used to generate them."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4a0b1c2d3e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ticket_suggested_answers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("ai_content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status = 'draft'", name="ck_ticket_suggested_answers_status"),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ticket_suggested_answers_ticket_id"),
        "ticket_suggested_answers",
        ["ticket_id"],
    )
    op.create_table(
        "ticket_suggested_answer_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("draft_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["draft_id"], ["ticket_suggested_answers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "draft_id", "position", name="uq_ticket_suggested_answer_source_position"
        ),
    )
    op.create_index(
        op.f("ix_ticket_suggested_answer_sources_draft_id"),
        "ticket_suggested_answer_sources",
        ["draft_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_ticket_suggested_answer_sources_draft_id"),
        table_name="ticket_suggested_answer_sources",
    )
    op.drop_table("ticket_suggested_answer_sources")
    op.drop_index(
        op.f("ix_ticket_suggested_answers_ticket_id"),
        table_name="ticket_suggested_answers",
    )
    op.drop_table("ticket_suggested_answers")
