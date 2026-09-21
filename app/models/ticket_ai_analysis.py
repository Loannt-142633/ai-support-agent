"""AI analysis result model for support tickets."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.ticket import Ticket, TicketCategory, TicketPriority


class TicketAIAnalysis(Base):
    """Persisted AI classification and summarization output for a ticket."""

    __tablename__ = "ticket_ai_analysis"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticket_id: Mapped[UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    predicted_category: Mapped[TicketCategory] = mapped_column(
        Enum(
            TicketCategory,
            values_callable=lambda enum: [item.value for item in enum],
            name="ticket_ai_predicted_category",
        ),
        nullable=False,
    )
    predicted_priority: Mapped[TicketPriority] = mapped_column(
        Enum(
            TicketPriority,
            values_callable=lambda enum: [item.value for item in enum],
            name="ticket_ai_predicted_priority",
        ),
        nullable=False,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    requires_human: Mapped[bool] = mapped_column(Boolean, nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    ticket: Mapped["Ticket"] = relationship(back_populates="ai_analyses")
