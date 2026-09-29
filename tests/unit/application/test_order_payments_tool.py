import asyncio
import json
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from app.db.base import Base
from app.models import User  # noqa: F401
from app.models.ticket import Ticket
from app.repositories.fake_order_payments_repository import (
    DEMO_CUSTOMER_ID,
    FakeOrderPaymentsRepository,
)
from app.repositories.ticket_repository import TicketRepository
from app.services.order_payments_service import OrderPaymentsService
from app.tools.order_payments import (
    StaffToolDispatcher,
    ToolExecutionContext,
    get_order_payments_declaration,
    load_tool_context,
)
from google.genai import types
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def test_gemini_declaration_exposes_only_order_id() -> None:
    declaration = get_order_payments_declaration()
    assert isinstance(declaration, types.FunctionDeclaration)
    assert declaration.name == "get_order_payments"
    assert declaration.parameters is not None
    assert set(declaration.parameters.properties or {}) == {"order_id"}
    assert declaration.parameters.required == ["order_id"]
    assert declaration.parameters.additional_properties is False
    assert declaration.parameters.properties is not None
    assert declaration.parameters.properties["order_id"].type == types.Type.STRING
    assert "duplicate charge" in (declaration.description or "")
    assert "refund eligibility" in (declaration.description or "")


def test_dispatch_uses_customer_from_loaded_ticket() -> None:
    customer_id = uuid4()
    ticket = Ticket(id=uuid4(), user_id=customer_id)
    tickets = Mock()
    tickets.get = AsyncMock(return_value=ticket)
    service = Mock(spec=OrderPaymentsService)
    expected = asyncio.run(
        OrderPaymentsService(FakeOrderPaymentsRepository(demo_customer_id=customer_id))
        .get_order_payments("ORD-DEMO-SINGLE", ticket_user_id=customer_id)
    )
    service.get_order_payments = AsyncMock(return_value=expected)

    async def run() -> dict[str, object]:
        context = await load_tool_context(ticket.id, tickets)
        return await StaffToolDispatcher(service).dispatch(
            "get_order_payments", {"order_id": "ORD-DEMO-SINGLE"}, context
        )

    result = asyncio.run(run())
    tickets.get.assert_awaited_once_with(ticket.id)
    service.get_order_payments.assert_awaited_once_with(
        "ORD-DEMO-SINGLE", ticket_user_id=customer_id
    )
    assert result["status"] == "found"


def test_missing_ticket_cannot_create_context() -> None:
    tickets = Mock()
    tickets.get = AsyncMock(return_value=None)
    with pytest.raises(LookupError, match="Ticket not found"):
        asyncio.run(load_tool_context(uuid4(), tickets))


def test_context_loads_ticket_customer_from_database() -> None:
    async def run() -> None:
        engine = create_async_engine("sqlite+aiosqlite://")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as session:
                customer = User(id=DEMO_CUSTOMER_ID, name="Demo", email="demo@example.invalid")
                ticket = Ticket(
                    id=uuid4(),
                    user_id=DEMO_CUSTOMER_ID,
                    title="Payment question",
                    description="Check order",
                )
                session.add_all([customer, ticket])
                await session.commit()
                ticket_id = ticket.id
            async with sessions() as session:
                context = await load_tool_context(ticket_id, TicketRepository(session))
                result = await StaffToolDispatcher(
                    OrderPaymentsService(FakeOrderPaymentsRepository())
                ).dispatch("get_order_payments", {"order_id": "ORD-DEMO-SINGLE"}, context)
                assert context.ticket.user_id == DEMO_CUSTOMER_ID
                assert result["status"] == "found"
        finally:
            await engine.dispose()

    asyncio.run(run())


@pytest.mark.parametrize(
    ("order_id", "status", "count"),
    [
        ("ORD-DEMO-DOUBLE", "found", 2),
        ("ORD-DEMO-RETRY", "found", 2),
        ("ORD-DEMO-EMPTY", "found", 0),
        ("ORD-DEMO-MISSING", "not_found", 0),
    ],
)
def test_dispatch_serializes_demo_facts(order_id: str, status: str, count: int) -> None:
    dispatcher = StaffToolDispatcher(OrderPaymentsService(FakeOrderPaymentsRepository()))
    context = ToolExecutionContext(Ticket(id=uuid4(), user_id=DEMO_CUSTOMER_ID))
    result = asyncio.run(dispatcher.dispatch("get_order_payments", {"order_id": order_id}, context))

    assert result["order_id"] == order_id
    assert result["status"] == status
    assert isinstance(result["payments"], list)
    assert len(result["payments"]) == count
    assert result["source"] == {
        "name": "fake_order_payments",
        "is_simulated": True,
        "description": "Simulated demo data; not a payment provider result.",
    }
    encoded = json.dumps(result)
    assert "user_id" not in encoded
    if count:
        payments = result["payments"]
        assert isinstance(payments, list)
        assert all(p["amount"] == "125000.00" for p in payments)
        assert all(p["currency"] == "VND" for p in payments)
        assert all(p["created_at"].endswith("+00:00") for p in payments)
        assert all(p["completed_at"].endswith("+00:00") for p in payments)
        assert all(p["order_id"] == order_id for p in payments)
        assert [p["status"] for p in payments] == (
            ["failed", "succeeded"] if order_id == "ORD-DEMO-RETRY" else ["succeeded"] * count
        )


def test_customer_mismatch_returns_safe_error() -> None:
    dispatcher = StaffToolDispatcher(OrderPaymentsService(FakeOrderPaymentsRepository()))
    context = ToolExecutionContext(Ticket(id=uuid4(), user_id=uuid4()))
    result = asyncio.run(
        dispatcher.dispatch("get_order_payments", {"order_id": "ORD-DEMO-DOUBLE"}, context)
    )
    assert result == {
        "status": "error",
        "error": {"code": "access_denied", "message": "Order is not available for this ticket"},
    }


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        None,
        {"order_id": 123},
        {"order_id": ""},
        {"order_id": "  "},
        {"order_id": "ORD-DEMO-SINGLE", "ticket_user_id": str(DEMO_CUSTOMER_ID)},
        {"order_id": "ORD-DEMO-SINGLE", "staff_id": "admin"},
        {"order_id": "ORD-DEMO-SINGLE", "authorized": True},
    ],
)
def test_invalid_or_injected_arguments_never_call_service(arguments: object) -> None:
    service = Mock(spec=OrderPaymentsService)
    service.get_order_payments = AsyncMock()
    context = ToolExecutionContext(Ticket(id=uuid4(), user_id=uuid4()))
    result = asyncio.run(
        StaffToolDispatcher(service).dispatch("get_order_payments", arguments, context)
    )
    assert result["status"] == "error"
    assert result["error"] == {
        "code": "invalid_arguments",
        "message": "Expected only a non-empty string order_id",
    }
    service.get_order_payments.assert_not_awaited()


def test_injected_customer_cannot_bypass_real_ticket_customer() -> None:
    dispatcher = StaffToolDispatcher(OrderPaymentsService(FakeOrderPaymentsRepository()))
    context = ToolExecutionContext(Ticket(id=uuid4(), user_id=uuid4()))
    result = asyncio.run(
        dispatcher.dispatch(
            "get_order_payments",
            {"order_id": "ORD-DEMO-SINGLE", "ticket_user_id": str(DEMO_CUSTOMER_ID)},
            context,
        )
    )
    assert result["error"]["code"] == "invalid_arguments"


def test_unknown_tool_is_not_executed() -> None:
    service = Mock(spec=OrderPaymentsService)
    service.get_order_payments = AsyncMock()
    context = ToolExecutionContext(Ticket(id=uuid4(), user_id=DEMO_CUSTOMER_ID))
    result = asyncio.run(
        StaffToolDispatcher(service).dispatch("search_knowledge_base", {"order_id": "X"}, context)
    )
    assert result["error"] == {"code": "unknown_tool", "message": "Tool is not available"}
    service.get_order_payments.assert_not_awaited()


def test_payment_source_failure_is_logged_and_redacted(caplog: pytest.LogCaptureFixture) -> None:
    service = Mock(spec=OrderPaymentsService)
    service.get_order_payments = AsyncMock(side_effect=RuntimeError("private provider token"))
    context = ToolExecutionContext(Ticket(id=uuid4(), user_id=DEMO_CUSTOMER_ID))
    result = asyncio.run(
        StaffToolDispatcher(service).dispatch("get_order_payments", {"order_id": "X"}, context)
    )
    assert result["error"] == {
        "code": "source_unavailable",
        "message": "Payment data is temporarily unavailable",
    }
    assert "private provider token" not in json.dumps(result)
    assert "Payment source failed" in caplog.text
