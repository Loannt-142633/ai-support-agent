"""Send an approved answer and persist the transport outcome."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket_suggested_answer import TicketSuggestedAnswer
from app.repositories.ticket_repository import TicketRepository
from app.repositories.ticket_suggested_answer_repository import TicketSuggestedAnswerRepository
from app.services.email_sender import EmailDeliveryError, EmailSender


class SuggestedAnswerNotSendableError(Exception):
    """Only an approved draft can start email delivery."""


class SuggestedAnswerRecipientMissingError(Exception):
    """The ticket no longer has a customer email address."""


class SuggestedAnswerDeliveryFailedError(Exception):
    """The sender reported failure, which was saved on the draft."""


class SuggestedAnswerDeliveryService:
    """Commit pending_send before SMTP, then record its confirmed outcome."""

    def __init__(
        self,
        tickets: TicketRepository,
        drafts: TicketSuggestedAnswerRepository,
        sender: EmailSender,
        session: AsyncSession,
    ) -> None:
        self._tickets = tickets
        self._drafts = drafts
        self._sender = sender
        self._session = session

    async def send(self, ticket_id: UUID, draft_id: UUID) -> TicketSuggestedAnswer:
        try:
            draft = await self._drafts.get_for_ticket_for_update(
                ticket_id=ticket_id, draft_id=draft_id
            )
            if draft is None:
                raise LookupError("Suggested answer not found")
            if draft.status != "approved":
                raise SuggestedAnswerNotSendableError("Only an approved draft can be sent")

            ticket = await self._tickets.get_with_user(ticket_id)
            if ticket is None or ticket.user is None:
                raise SuggestedAnswerRecipientMissingError("Ticket has no customer email address")

            recipient = ticket.user.email
            subject = f"Re: {ticket.title}"
            body = draft.staff_content or draft.ai_content
            now = datetime.now(UTC)
            draft.status = "pending_send"
            draft.recipient_email = recipient
            draft.send_started_at = now
            draft.updated_at = now
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        try:
            await self._sender.send(to_email=recipient, subject=subject, body=body)
        except Exception as error:
            reason = str(error) if isinstance(error, EmailDeliveryError) else "Email sender failed"
            reason = (reason or "Email delivery failed")[:255]
            await self._record_outcome(ticket_id, draft_id, status="send_failed", reason=reason)
            raise SuggestedAnswerDeliveryFailedError("Email delivery failed") from error

        return await self._record_outcome(ticket_id, draft_id, status="sent")

    async def _record_outcome(
        self,
        ticket_id: UUID,
        draft_id: UUID,
        *,
        status: Literal["sent", "send_failed"],
        reason: str | None = None,
    ) -> TicketSuggestedAnswer:
        try:
            draft = await self._drafts.get_for_ticket_for_update(
                ticket_id=ticket_id, draft_id=draft_id
            )
            if draft is None or draft.status != "pending_send":
                raise RuntimeError("Pending email delivery record is missing")
            now = datetime.now(UTC)
            draft.status = status
            draft.updated_at = now
            if status == "sent":
                draft.sent_at = now
            else:
                draft.send_failure_reason = reason
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return draft
