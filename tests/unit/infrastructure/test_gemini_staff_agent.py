import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from app.llm.exceptions import LLMInvalidResponseError, LLMProviderError, LLMTimeoutError
from app.llm.providers.gemini_staff_agent import GeminiStaffAgentModel
from app.models.ticket import Ticket
from app.repositories.fake_order_payments_repository import (
    DEMO_CUSTOMER_ID,
    FakeOrderPaymentsRepository,
)
from app.services.agent_service import AgentService
from app.services.order_payments_service import OrderPaymentsService
from app.tools.order_payments import StaffToolDispatcher, ToolExecutionContext
from google.genai import types


def _response(*parts: types.Part) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=list(parts)))]
    )


def _model(*responses: object) -> tuple[GeminiStaffAgentModel, AsyncMock]:
    client = MagicMock()
    generate = AsyncMock(side_effect=list(responses))
    client.aio.models.generate_content = generate
    return (
        GeminiStaffAgentModel(api_key="", model="gemini-test", timeout=2, client=client),
        generate,
    )


def test_gemini_receives_tool_result_with_original_call_and_returns_answer() -> None:
    call = types.FunctionCall(
        id="call-1", name="get_order_payments", args={"order_id": "ORD-DEMO-SINGLE"}
    )
    first = _response(types.Part(function_call=call))
    second = _response(types.Part.from_text(text="This demo order has one successful payment."))
    model, generate = _model(first, second)
    service = AgentService(
        model, StaffToolDispatcher(OrderPaymentsService(FakeOrderPaymentsRepository()))
    )
    context = ToolExecutionContext(Ticket(id=uuid4(), user_id=DEMO_CUSTOMER_ID))

    answer = asyncio.run(service.answer("Check the order", context=context))

    assert answer == "This demo order has one successful payment."
    assert generate.await_count == 2
    first_kwargs = generate.await_args_list[0].kwargs
    first_config = first_kwargs["config"]
    assert first_kwargs["model"] == "gemini-test"
    assert first_config.tools[0].function_declarations[0].name == "get_order_payments"
    assert first_config.automatic_function_calling.disable is True
    assert first_kwargs["contents"][0].parts[0].text == "Check the order"

    second_kwargs = generate.await_args_list[1].kwargs
    second_config = second_kwargs["config"]
    assert (
        second_config.tool_config.function_calling_config.mode
        == types.FunctionCallingConfigMode.NONE
    )
    contents = second_kwargs["contents"]
    assert contents[0].parts[0].text == "Check the order"
    assert contents[1] is first.candidates[0].content
    function_response = contents[2].parts[0].function_response
    assert function_response.name == "get_order_payments"
    assert function_response.id == "call-1"
    assert function_response.response["status"] == "found"
    assert function_response.response["source"]["is_simulated"] is True
    assert function_response.response["payments"][0]["amount"] == "125000.00"


def test_gemini_direct_text_uses_one_request() -> None:
    model, generate = _model(_response(types.Part.from_text(text="Please provide an order ID.")))
    service = AgentService(
        model, StaffToolDispatcher(OrderPaymentsService(FakeOrderPaymentsRepository()))
    )
    context = ToolExecutionContext(Ticket(id=uuid4(), user_id=DEMO_CUSTOMER_ID))
    answer = asyncio.run(service.answer("Help", context=context))
    assert answer == "Please provide an order ID."
    generate.assert_awaited_once()


def test_gemini_tool_call_cannot_inject_customer_id() -> None:
    first = _response(
        types.Part(function_call=types.FunctionCall(
            name="get_order_payments",
            args={"order_id": "ORD-DEMO-SINGLE", "ticket_user_id": str(DEMO_CUSTOMER_ID)},
        ))
    )
    model, generate = _model(first, _response(types.Part.from_text(text="Invalid arguments.")))
    context = ToolExecutionContext(Ticket(id=uuid4(), user_id=uuid4()))
    service = AgentService(
        model, StaffToolDispatcher(OrderPaymentsService(FakeOrderPaymentsRepository()))
    )
    assert asyncio.run(service.answer("Paid?", context=context)) == "Invalid arguments."
    contents = generate.await_args_list[1].kwargs["contents"]
    assert contents[2].parts[0].function_response.response["error"]["code"] == "invalid_arguments"


def test_gemini_empty_response_is_rejected() -> None:
    model, _ = _model(types.GenerateContentResponse(candidates=[]))
    with pytest.raises(LLMInvalidResponseError):
        asyncio.run(model.start("Question"))


@pytest.mark.parametrize(
    ("failure", "expected"),
    [(TimeoutError(), LLMTimeoutError), (RuntimeError("private key"), LLMProviderError)],
)
def test_gemini_failures_are_translated(failure: Exception, expected: type[Exception]) -> None:
    model, _ = _model(failure)
    with pytest.raises(expected, match="Gemini"):
        asyncio.run(model.start("Question"))
