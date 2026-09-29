"""Customer-scoped internal lookup for future staff tools."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from app.services.order_payments import OrderPaymentsRepository, Payment, PaymentDataSource


class OrderPaymentsAccessError(PermissionError):
    """The ticket customer is missing or does not own this order."""


@dataclass(frozen=True)
class OrderPaymentsResult:
    """Stable result shape; not_found is distinct from an empty payment history."""

    order_id: str
    status: Literal["found", "not_found"]
    user_id: UUID | None
    payments: tuple[Payment, ...]
    source: PaymentDataSource


class OrderPaymentsService:
    """Read payment facts without inferring duplicate charges or authorizing staff."""

    def __init__(self, repository: OrderPaymentsRepository) -> None:
        self._repository = repository

    async def get_order_payments(
        self, order_id: str, *, ticket_user_id: UUID | None
    ) -> OrderPaymentsResult:
        """Require the user_id from a trusted, loaded ticket, never an LLM argument.

        The caller must separately authenticate staff and authorize ticket access.
        This ownership check alone is not permission to expose payment data.
        """
        if ticket_user_id is None:
            raise OrderPaymentsAccessError("Ticket has no customer")
        if not order_id.strip():
            raise ValueError("order_id must not be blank")
        order = await self._repository.get(order_id)
        if order is None:
            return OrderPaymentsResult(order_id, "not_found", None, (), self._repository.source)
        if order.user_id != ticket_user_id:
            raise OrderPaymentsAccessError("Order does not belong to the ticket customer")
        return OrderPaymentsResult(
            order.order_id, "found", order.user_id, order.payments, self._repository.source
        )
