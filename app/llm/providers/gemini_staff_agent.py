"""Gemini adapter for the bounded internal staff-agent conversation."""

import asyncio
from dataclasses import dataclass

from google import genai
from google.genai import types

from app.llm.exceptions import LLMInvalidResponseError, LLMProviderError, LLMTimeoutError
from app.services.agent_service import AgentToolCall, AgentTurn
from app.tools.order_payments import get_order_payments_declaration

SYSTEM_INSTRUCTION = (
    "You assist support staff with the current ticket. Use get_order_payments only to inspect "
    "payment attempts. For questions about an order's payment history, call the tool first. "
    "Payment tool data may be simulated; identify it as demo data "
    "when so marked. "
    "Do not claim a duplicate charge or refund eligibility from payment attempts alone. "
    "Do not invent payment facts when the tool reports an error or an order is not found."
)


@dataclass(frozen=True)
class _GeminiContinuation:
    question: str
    model_content: types.Content


class GeminiStaffAgentModel:
    """Send one question and, when requested, one tool response back to Gemini."""

    def __init__(
        self, *, api_key: str, model: str, timeout: float, client: genai.Client | None = None
    ) -> None:
        if not api_key.strip() and client is None:
            raise ValueError("api_key cannot be empty")
        if not model.strip():
            raise ValueError("model cannot be empty")
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        self._model = model
        self._timeout = timeout
        self._client = client or genai.Client(api_key=api_key)

    async def start(self, question: str) -> AgentTurn:
        """Offer Gemini the one declared tool, without automatic SDK execution."""
        contents = [types.Content(role="user", parts=[types.Part.from_text(text=question)])]
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=[types.Tool(function_declarations=[get_order_payments_declaration()])],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        response = await self._generate(contents=contents, config=config)
        return self._read_turn(response, question=question)

    async def finish(self, turn: AgentTurn, tool_result: dict[str, object]) -> AgentTurn:
        """Echo Gemini's first model content, then its matching function response."""
        if len(turn.tool_calls) != 1 or not isinstance(turn.continuation, _GeminiContinuation):
            raise ValueError("No single Gemini function call to continue")
        call = turn.tool_calls[0]
        function_response = types.FunctionResponse(
            name=call.name, id=call.call_id, response=tool_result
        )
        contents = [
            types.Content(
                role="user", parts=[types.Part.from_text(text=turn.continuation.question)]
            ),
            turn.continuation.model_content,
            types.Content(role="user", parts=[types.Part(function_response=function_response)]),
        ]
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=[types.Tool(function_declarations=[get_order_payments_declaration()])],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode=types.FunctionCallingConfigMode.NONE
                )
            ),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        response = await self._generate(contents=contents, config=config)
        return self._read_turn(response, question=turn.continuation.question)

    async def _generate(
        self, *, contents: list[types.Content], config: types.GenerateContentConfig
    ) -> types.GenerateContentResponse:
        try:
            return await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self._model, contents=contents, config=config
                ),
                timeout=self._timeout,
            )
        except TimeoutError as error:
            raise LLMTimeoutError("Gemini request timed out") from error
        except Exception as error:
            raise LLMProviderError("Gemini provider request failed") from error

    @staticmethod
    def _read_turn(response: types.GenerateContentResponse, *, question: str) -> AgentTurn:
        if not response.candidates or response.candidates[0].content is None:
            raise LLMInvalidResponseError("Gemini returned no content")
        content = response.candidates[0].content
        calls = tuple(
            AgentToolCall(
                part.function_call.name or "",
                part.function_call.args or {},
                part.function_call.id,
            )
            for part in (content.parts or [])
            if part.function_call is not None
        )
        return AgentTurn(
            text=response.text,
            tool_calls=calls,
            continuation=_GeminiContinuation(question, content),
        )
