import asyncio
from dataclasses import FrozenInstanceError
from decimal import Decimal
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from app.repositories.fake_order_payments_repository import (
    DEMO_CUSTOMER_ID,
    FakeOrderPaymentsRepository,
)
from app.services.order_payments import OrderPaymentsRepository, PaymentStatus
from app.services.order_payments_service import OrderPaymentsAccessError, OrderPaymentsService


@pytest.mark.parametrize(
    ("order_id", "statuses", "successful_amount"),
    [
        ("ORD-DEMO-SINGLE", ["succeeded"], "125000.00"),
        ("ORD-DEMO-DOUBLE", ["succeeded", "succeeded"], "250000.00"),
        ("ORD-DEMO-RETRY", ["failed", "succeeded"], "125000.00"),
        ("ORD-DEMO-EMPTY", [], "0"),
    ],
)
def test_demo_payment_facts(order_id: str, statuses: list[str], successful_amount: str) -> None:
    service = OrderPaymentsService(FakeOrderPaymentsRepository())
    result = asyncio.run(service.get_order_payments(order_id, ticket_user_id=DEMO_CUSTOMER_ID))

    assert result.status == "found"
    assert result.order_id == order_id
    assert result.user_id == DEMO_CUSTOMER_ID
    assert result.source.is_simulated is True
    assert "not a payment provider" in result.source.description
    assert [payment.status.value for payment in result.payments] == statuses
    successful = [p for p in result.payments if p.status == PaymentStatus.SUCCEEDED]
    assert sum((p.amount for p in successful), Decimal("0")) == Decimal(successful_amount)
    assert len({p.payment_id for p in result.payments}) == len(result.payments)
    for payment in result.payments:
        assert payment.order_id == order_id
        assert payment.amount == Decimal("125000.00")
        assert isinstance(payment.amount, Decimal)
        assert payment.currency == "VND"
        assert payment.created_at.utcoffset() is not None
        assert payment.completed_at > payment.created_at


def test_unknown_order_is_distinct_from_order_without_payments() -> None:
    service = OrderPaymentsService(FakeOrderPaymentsRepository())
    result = asyncio.run(
        service.get_order_payments("ORD-DEMO-MISSING", ticket_user_id=DEMO_CUSTOMER_ID)
    )
    assert result.status == "not_found"
    assert result.order_id == "ORD-DEMO-MISSING"
    assert result.user_id is None
    assert result.payments == ()
    assert result.source.is_simulated is True


@pytest.mark.parametrize("order_id", ["ORD-DEMO-SINGLE", "ORD-DEMO-EMPTY"])
def test_other_customer_cannot_read_order(order_id: str) -> None:
    service = OrderPaymentsService(FakeOrderPaymentsRepository())
    with pytest.raises(OrderPaymentsAccessError, match="does not belong"):
        asyncio.run(service.get_order_payments(order_id, ticket_user_id=uuid4()))


def test_ticket_without_customer_is_rejected_before_lookup() -> None:
    repository = Mock(spec=OrderPaymentsRepository)
    repository.get = AsyncMock()
    with pytest.raises(OrderPaymentsAccessError, match="no customer"):
        asyncio.run(
            OrderPaymentsService(repository).get_order_payments(
                "ORD-DEMO-SINGLE", ticket_user_id=None
            )
        )
    repository.get.assert_not_awaited()


def test_demo_can_be_bound_to_existing_ticket_customer() -> None:
    customer_id = uuid4()
    service = OrderPaymentsService(FakeOrderPaymentsRepository(demo_customer_id=customer_id))
    result = asyncio.run(service.get_order_payments("ORD-DEMO-SINGLE", ticket_user_id=customer_id))
    assert result.user_id == customer_id
    with pytest.raises(OrderPaymentsAccessError):
        asyncio.run(service.get_order_payments("ORD-DEMO-SINGLE", ticket_user_id=DEMO_CUSTOMER_ID))


def test_results_are_repeatable_and_cannot_mutate_fixtures() -> None:
    async def read() -> None:
        first = await FakeOrderPaymentsRepository().get("ORD-DEMO-DOUBLE")
        second = await FakeOrderPaymentsRepository().get("ORD-DEMO-DOUBLE")
        assert first == second
        assert first is not None
        assert [p.payment_id for p in first.payments] == ["PAY-DOUBLE-01", "PAY-DOUBLE-02"]
        with pytest.raises(FrozenInstanceError):
            first.payments[0].amount = Decimal("1")  # type: ignore[misc]

    asyncio.run(read())


def test_service_accepts_another_repository_implementation() -> None:
    repository = Mock(spec=OrderPaymentsRepository)
    repository.source = FakeOrderPaymentsRepository().source
    repository.get = AsyncMock(return_value=None)
    result = asyncio.run(
        OrderPaymentsService(repository).get_order_payments(
            "OTHER", ticket_user_id=DEMO_CUSTOMER_ID
        )
    )
    assert result.status == "not_found"
    repository.get.assert_awaited_once_with("OTHER")


@pytest.mark.parametrize("order_id", ["", "   "])
def test_blank_order_id_is_rejected(order_id: str) -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        asyncio.run(
            OrderPaymentsService(FakeOrderPaymentsRepository()).get_order_payments(
                order_id, ticket_user_id=DEMO_CUSTOMER_ID
            )
        )
