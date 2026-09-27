"""Persisted AI-generated answer drafts and their retrieved sources."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.ticket import Ticket


class TicketSuggestedAnswer(Base):
    """An unsent, reviewable answer draft for one support ticket."""

    __tablename__ = "ticket_suggested_answers"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'approved', 'rejected')",
            name="ck_ticket_suggested_answers_status",
        ),
        CheckConstraint(
            "(status = 'draft' AND reviewed_at IS NULL AND rejection_reason IS NULL) OR "
            "(status = 'approved' AND reviewed_at IS NOT NULL AND rejection_reason IS NULL) OR "
            "(status = 'rejected' AND reviewed_at IS NOT NULL AND rejection_reason IS NOT NULL)",
            name="ck_ticket_suggested_answers_review",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    ai_content: Mapped[str] = mapped_column(Text, nullable=False)
    staff_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    ticket: Mapped["Ticket"] = relationship(back_populates="suggested_answers")
    sources: Mapped[list["TicketSuggestedAnswerSource"]] = relationship(
        back_populates="draft",
        cascade="all, delete-orphan",
        order_by="TicketSuggestedAnswerSource.position",
    )


class TicketSuggestedAnswerSource(Base):
    """Identity of a chunk used to generate a draft, kept in prompt order."""

    __tablename__ = "ticket_suggested_answer_sources"
    __table_args__ = (
        UniqueConstraint("draft_id", "position", name="uq_ticket_suggested_answer_source_position"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    draft_id: Mapped[UUID] = mapped_column(
        ForeignKey("ticket_suggested_answers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    document_id: Mapped[UUID] = mapped_column(nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    draft: Mapped["TicketSuggestedAnswer"] = relationship(back_populates="sources")
