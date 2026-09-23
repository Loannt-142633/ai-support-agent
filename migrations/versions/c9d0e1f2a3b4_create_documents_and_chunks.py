"""Create policy documents and vector chunks tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "b7c8d9e0f1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


EMBEDDING_DIMENSION = 768


def upgrade() -> None:
    """Create policy document and document chunk storage."""

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("storage_path", sa.String(length=1000), nullable=False),
        sa.Column("document_type", sa.String(length=100), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=True),
        sa.Column("embedding_model", sa.String(length=255), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_documents_uploaded_by"),
        "documents",
        ["uploaded_by"],
        unique=False,
    )

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSION), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"),
    )
    op.create_index(
        op.f("ix_document_chunks_document_id"),
        "document_chunks",
        ["document_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop policy document and document chunk storage."""

    op.drop_index(op.f("ix_document_chunks_document_id"), table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index(op.f("ix_documents_uploaded_by"), table_name="documents")
    op.drop_table("documents")
    op.execute("DROP EXTENSION IF EXISTS vector")
