"""Deterministic demo data only; no payment provider or database is consulted."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from app.services.order_payments import OrderPayments, Payment, PaymentDataSource, PaymentStatus

DEMO_CUSTOMER_ID = UUID("00000000-0000-4000-8000-000000000001")


class FakeOrderPaymentsRepository:
    """In-memory fixtures; optionally bind them to an existing demo ticket customer.

    Binding is an explicit demo setup operation, not a production ownership mapping.
    """

    def __init__(self, *, demo_customer_id: UUID = DEMO_CUSTOMER_ID) -> None:
        created_at = datetime(2026, 1, 15, 10, 0, tzinfo=UTC)

        def payment(order_id: str, suffix: str, status: PaymentStatus, minute: int) -> Payment:
            started = created_at + timedelta(minutes=minute)
            return Payment(
                payment_id=f"PAY-{suffix}",
                order_id=order_id,
                amount=Decimal("125000.00"),
                currency="VND",
                status=status,
                created_at=started,
                completed_at=started + timedelta(seconds=5),
            )

        succeeded = PaymentStatus.SUCCEEDED
        failed = PaymentStatus.FAILED
        self._orders = {
            order_id: OrderPayments(order_id, demo_customer_id, payments)
            for order_id, payments in (
                ("ORD-DEMO-SINGLE", (payment("ORD-DEMO-SINGLE", "SINGLE-01", succeeded, 0),)),
                (
                    "ORD-DEMO-DOUBLE",
                    (
                        payment("ORD-DEMO-DOUBLE", "DOUBLE-01", succeeded, 0),
                        payment("ORD-DEMO-DOUBLE", "DOUBLE-02", succeeded, 1),
                    ),
                ),
                (
                    "ORD-DEMO-RETRY",
                    (
                        payment("ORD-DEMO-RETRY", "RETRY-01", failed, 0),
                        payment("ORD-DEMO-RETRY", "RETRY-02", succeeded, 1),
                    ),
                ),
                ("ORD-DEMO-EMPTY", ()),
            )
        }

    @property
    def source(self) -> PaymentDataSource:
        """Never represent these fixtures as provider-confirmed payments."""
        return PaymentDataSource(
            name="fake_order_payments",
            is_simulated=True,
            description="Simulated demo data; not a payment provider result.",
        )

    async def get(self, order_id: str) -> OrderPayments | None:
        """Read an immutable snapshot; unknown IDs are not synthesized."""
        return self._orders.get(order_id)
