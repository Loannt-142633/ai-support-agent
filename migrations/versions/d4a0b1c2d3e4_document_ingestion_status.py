"""Track document ingestion status and a short failure reason."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4a0b1c2d3e4"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
    )
    op.add_column("documents", sa.Column("failure_reason", sa.String(length=255), nullable=True))
    op.create_check_constraint(
        "ck_documents_status",
        "documents",
        "status IN ('pending', 'processing', 'completed', 'failed')",
    )
    op.execute(
        "UPDATE documents SET status = 'completed' "
        "WHERE EXISTS (SELECT 1 FROM document_chunks "
        "WHERE document_chunks.document_id = documents.id)"
    )


def downgrade() -> None:
    op.drop_constraint("ck_documents_status", "documents", type_="check")
    op.drop_column("documents", "failure_reason")
    op.drop_column("documents", "status")
