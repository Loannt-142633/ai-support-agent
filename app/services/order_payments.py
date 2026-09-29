"""Immutable payment records and the replaceable order data boundary."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class PaymentStatus(StrEnum):
    """Outcome of a payment attempt, not the status of the order."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class Payment:
    """A payment attempt; amounts use Decimal and timestamps include a timezone."""

    payment_id: str
    order_id: str
    amount: Decimal
    currency: str
    status: PaymentStatus
    created_at: datetime
    completed_at: datetime


@dataclass(frozen=True)
class OrderPayments:
    """An existing order, including orders without payment attempts."""

    order_id: str
    user_id: UUID
    payments: tuple[Payment, ...]


@dataclass(frozen=True)
class PaymentDataSource:
    """Explicit provenance, also returned for unsuccessful lookups."""

    name: str
    is_simulated: bool
    description: str


class OrderPaymentsRepository(Protocol):
    """Replace with a payment-system adapter without changing the use case."""

    @property
    def source(self) -> PaymentDataSource: ...

    async def get(self, order_id: str) -> OrderPayments | None:
        """Return an order with all attempts, or None when it does not exist."""
        ...
