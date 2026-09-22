"""Provider-agnostic LLM abstraction."""

from typing import Protocol, TypeVar

from pydantic import BaseModel

from app.llm.exceptions import (
	LLMError,
	LLMInvalidResponseError,
	LLMProviderError,
	LLMRateLimitError,
	LLMTimeoutError,
)

OutputModel = TypeVar("OutputModel", bound=BaseModel)


class LLMClient(Protocol):
	"""Contract implemented by future AI provider adapters."""

	async def generate_structured(
		self,
		*,
		prompt: str,
		response_model: type[OutputModel],
	) -> OutputModel:
		"""Generate and validate a structured response from a prompt."""

__all__ = [
	"LLMClient",
	"LLMError",
	"LLMInvalidResponseError",
	"LLMProviderError",
	"LLMRateLimitError",
	"LLMTimeoutError",
]
