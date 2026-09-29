import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.models.ticket import Ticket
from app.services.agent_service import (
    AgentInvalidResponseError,
    AgentService,
    AgentToolCall,
    AgentTurn,
)
from app.tools.order_payments import ToolExecutionContext


def _context() -> ToolExecutionContext:
    return ToolExecutionContext(Ticket(id=uuid4(), user_id=uuid4()))


def test_agent_returns_direct_answer_without_dispatch() -> None:
    model = AsyncMock()
    model.start.return_value = AgentTurn("  Please review the ticket.  ")
    dispatcher = AsyncMock()

    answer = asyncio.run(AgentService(model, dispatcher).answer("Question", context=_context()))

    assert answer == "Please review the ticket."
    model.start.assert_awaited_once_with("Question")
    model.finish.assert_not_awaited()
    dispatcher.dispatch.assert_not_awaited()


def test_agent_passes_exact_dispatch_result_back_to_model() -> None:
    model = AsyncMock()
    first = AgentTurn(None, (AgentToolCall("get_order_payments", {"order_id": "ORD-1"}),))
    model.start.return_value = first
    model.finish.return_value = AgentTurn("Demo payment information.")
    dispatcher = AsyncMock()
    result = {"status": "found", "payments": [], "source": {"is_simulated": True}}
    dispatcher.dispatch.return_value = result
    context = _context()

    answer = asyncio.run(AgentService(model, dispatcher).answer("Paid?", context=context))

    assert answer == "Demo payment information."
    dispatcher.dispatch.assert_awaited_once_with(
        "get_order_payments", {"order_id": "ORD-1"}, context
    )
    model.finish.assert_awaited_once_with(first, result)


def test_agent_forwards_tool_error_for_model_to_explain() -> None:
    model = AsyncMock()
    first = AgentTurn(None, (AgentToolCall("get_order_payments", {"order_id": "X"}),))
    model.start.return_value = first
    model.finish.return_value = AgentTurn("The payment source is unavailable.")
    dispatcher = AsyncMock()
    dispatcher.dispatch.return_value = {
        "status": "error", "error": {"code": "source_unavailable"}
    }

    answer = asyncio.run(AgentService(model, dispatcher).answer("Paid?", context=_context()))

    assert answer == "The payment source is unavailable."
    assert model.finish.await_args.args[1] == dispatcher.dispatch.return_value


def test_blank_question_does_not_call_model() -> None:
    model = AsyncMock()
    with pytest.raises(ValueError, match="question must not be blank"):
        asyncio.run(AgentService(model, AsyncMock()).answer("  ", context=_context()))
    model.start.assert_not_awaited()


@pytest.mark.parametrize(
    "first",
    [
        AgentTurn(None),
        AgentTurn("  "),
        AgentTurn(None, (AgentToolCall("get_order_payments", {}), AgentToolCall("x", {}))),
    ],
)
def test_invalid_first_turn_does_not_dispatch(first: AgentTurn) -> None:
    model = AsyncMock()
    model.start.return_value = first
    dispatcher = AsyncMock()
    with pytest.raises(AgentInvalidResponseError):
        asyncio.run(AgentService(model, dispatcher).answer("Question", context=_context()))
    dispatcher.dispatch.assert_not_awaited()


@pytest.mark.parametrize(
    "final",
    [AgentTurn(None), AgentTurn("  "), AgentTurn(None, (AgentToolCall("x", {}),))],
)
def test_agent_rejects_empty_answer_or_second_tool_call(final: AgentTurn) -> None:
    model = AsyncMock()
    model.start.return_value = AgentTurn(None, (AgentToolCall("get_order_payments", {}),))
    model.finish.return_value = final
    with pytest.raises(AgentInvalidResponseError):
        asyncio.run(AgentService(model, AsyncMock()).answer("Question", context=_context()))
