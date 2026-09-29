"""Gemini declaration and controlled execution of the internal payment lookup."""

import logging
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from google.genai import types

from app.models.ticket import Ticket
from app.services.order_payments_service import (
    OrderPaymentsAccessError,
    OrderPaymentsResult,
    OrderPaymentsService,
)

logger = logging.getLogger(__name__)
TOOL_NAME = "get_order_payments"


def get_order_payments_declaration() -> types.FunctionDeclaration:
    """Expose only the order ID to Gemini; ticket identity stays in backend context."""
    return types.FunctionDeclaration(
        name=TOOL_NAME,
        description=(
            "View payment attempts for an order belonging to the current ticket customer. "
            "Returns recorded attempts and their source. Do not infer a duplicate charge "
            "or refund eligibility from this tool alone."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "order_id": types.Schema(type=types.Type.STRING, description="Order identifier")
            },
            required=["order_id"],
            additional_properties=False,
        ),
    )


class TicketReader(Protocol):
    """Read the ticket from trusted storage before any tool call is dispatched."""

    async def get(self, ticket_id: UUID) -> Ticket | None: ...


@dataclass(frozen=True)
class ToolExecutionContext:
    """Backend-owned context; never deserialize it from Gemini function arguments."""

    ticket: Ticket


async def load_tool_context(ticket_id: UUID, tickets: TicketReader) -> ToolExecutionContext:
    """Load a real ticket; the caller must first authorize staff access to it."""
    ticket = await tickets.get(ticket_id)
    if ticket is None:
        raise LookupError("Ticket not found")
    return ToolExecutionContext(ticket=ticket)


def _serialize_result(result: OrderPaymentsResult) -> dict[str, object]:
    return {
        "order_id": result.order_id,
        "status": result.status,
        "payments": [
            {
                "payment_id": payment.payment_id,
                "order_id": payment.order_id,
                "amount": str(payment.amount),
                "currency": payment.currency,
                "status": payment.status.value,
                "created_at": payment.created_at.isoformat(),
                "completed_at": payment.completed_at.isoformat(),
            }
            for payment in result.payments
        ],
        "source": {
            "name": result.source.name,
            "is_simulated": result.source.is_simulated,
            "description": result.source.description,
        },
    }


def _error(code: str, message: str) -> dict[str, object]:
    return {"status": "error", "error": {"code": code, "message": message}}


class StaffToolDispatcher:
    """Allowlisted tool execution; add explicit branches when more tools exist."""

    def __init__(self, order_payments: OrderPaymentsService) -> None:
        self._order_payments = order_payments

    async def dispatch(
        self, name: str, arguments: object, context: ToolExecutionContext
    ) -> dict[str, object]:
        """Execute a validated Gemini function call with backend-owned ticket context."""
        if name != TOOL_NAME:
            logger.warning("Rejected unregistered staff tool name %r", name)
            return _error("unknown_tool", "Tool is not available")

        if not isinstance(arguments, dict) or set(arguments) != {"order_id"}:
            logger.warning(
                "Rejected invalid %s arguments for ticket %s", TOOL_NAME, context.ticket.id
            )
            return _error("invalid_arguments", "Expected only a non-empty string order_id")
        order_id = arguments["order_id"]
        if not isinstance(order_id, str) or not order_id.strip():
            logger.warning("Rejected invalid order_id for ticket %s", context.ticket.id)
            return _error("invalid_arguments", "Expected only a non-empty string order_id")

        try:
            result = await self._order_payments.get_order_payments(
                order_id, ticket_user_id=context.ticket.user_id
            )
        except OrderPaymentsAccessError:
            logger.warning("Payment lookup denied for ticket %s", context.ticket.id)
            return _error("access_denied", "Order is not available for this ticket")
        except ValueError:
            logger.warning("Payment lookup rejected input for ticket %s", context.ticket.id)
            return _error("invalid_arguments", "Expected only a non-empty string order_id")
        except Exception:
            logger.exception("Payment source failed for ticket %s", context.ticket.id)
            return _error("source_unavailable", "Payment data is temporarily unavailable")
        return _serialize_result(result)
