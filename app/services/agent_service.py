"""One-turn staff question answering with at most one internal tool call."""

from dataclasses import dataclass
from typing import Protocol, TypeVar

ContextT = TypeVar("ContextT", contravariant=True)


class AgentInvalidResponseError(Exception):
    """The model did not provide one usable answer or requested extra tool work."""


@dataclass(frozen=True)
class AgentToolCall:
    """Untrusted name and arguments proposed by the model."""

    name: str
    arguments: object
    call_id: str | None = None


@dataclass(frozen=True)
class AgentTurn:
    """Provider-neutral turn, with opaque context for continuing the same exchange."""

    text: str | None
    tool_calls: tuple[AgentToolCall, ...] = ()
    continuation: object | None = None


class StaffAgentModel(Protocol):
    """Model boundary that preserves its own conversation state between turns."""

    async def start(self, question: str) -> AgentTurn: ...

    async def finish(self, turn: AgentTurn, tool_result: dict[str, object]) -> AgentTurn: ...


class StaffToolExecutor(Protocol[ContextT]):
    """Execute an allowlisted call against backend-owned context."""

    async def dispatch(
        self, name: str, arguments: object, context: ContextT
    ) -> dict[str, object]: ...


class AgentService[AgentContextT]:
    """Ask Gemini, execute one allowlisted tool call, then return the final answer."""

    def __init__(
        self, model: StaffAgentModel, dispatcher: StaffToolExecutor[AgentContextT]
    ) -> None:
        self._model = model
        self._dispatcher = dispatcher

    async def answer(self, question: str, *, context: AgentContextT) -> str:
        """Require backend-loaded ticket context; caller must authorize staff first."""
        if not question.strip():
            raise ValueError("question must not be blank")

        first = await self._model.start(question)
        if not first.tool_calls:
            return self._require_answer(first)
        if len(first.tool_calls) != 1:
            raise AgentInvalidResponseError("Expected at most one tool call")

        call = first.tool_calls[0]
        tool_result = await self._dispatcher.dispatch(call.name, call.arguments, context)
        final = await self._model.finish(first, tool_result)
        if final.tool_calls:
            raise AgentInvalidResponseError("Model requested another tool call")
        return self._require_answer(final)

    @staticmethod
    def _require_answer(turn: AgentTurn) -> str:
        if turn.text is None or not turn.text.strip():
            raise AgentInvalidResponseError("Model returned no answer")
        return turn.text.strip()
