"""Defer provider construction until a request really needs generation."""

from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel

from app.llm.client import LLMClient

OutputModel = TypeVar("OutputModel", bound=BaseModel)


class DeferredLLMClient:
    """Satisfy the LLM contract without connecting/configuring until called."""

    def __init__(self, factory: Callable[[], LLMClient]) -> None:
        self._factory = factory

    async def generate_structured(
        self,
        *,
        prompt: str,
        response_model: type[OutputModel],
    ) -> OutputModel:
        return await self._factory().generate_structured(
            prompt=prompt,
            response_model=response_model,
        )
