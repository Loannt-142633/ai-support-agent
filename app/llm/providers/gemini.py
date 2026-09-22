"""Google Gemini implementation of the LLM client contract."""

import asyncio
import json
from typing import Any, TypeVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

from app.llm.client import LLMClient
from app.llm.exceptions import (
    LLMInvalidResponseError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)

OutputModel = TypeVar("OutputModel", bound=BaseModel)


class GeminiLLMClient(LLMClient):
    """Generate structured responses through the Google Gemini API."""

    def __init__(self, *, api_key: str, model: str, timeout: float) -> None:
        if not api_key.strip():
            raise ValueError("api_key cannot be empty")
        if not model.strip():
            raise ValueError("model cannot be empty")
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")

        self._model = model
        self._timeout = timeout
        self._client = genai.Client(api_key=api_key)

    async def generate_structured(
        self,
        *,
        prompt: str,
        response_model: type[OutputModel],
    ) -> OutputModel:
        """Generate and validate structured output from Gemini."""

        try:
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=response_model,
                    ),
                ),
                timeout=self._timeout,
            )
        except TimeoutError as error:
            raise LLMTimeoutError("Gemini request timed out") from error
        except Exception as error:
            self._raise_provider_error(error)
            raise AssertionError("unreachable") from error

        return self._parse_response(response, response_model)

    @staticmethod
    def _parse_response(
        response: Any,
        response_model: type[OutputModel],
    ) -> OutputModel:
        """Convert Gemini's parsed or textual response into the requested model."""

        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            try:
                return response_model.model_validate(parsed)
            except ValidationError as error:
                raise LLMInvalidResponseError(
                    "Gemini returned structured data that failed validation"
                ) from error

        try:
            text = response.text
            if not text or not text.strip():
                raise ValueError("Gemini returned an empty response")
            return response_model.model_validate(json.loads(text))
        except (
            AttributeError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
            ValidationError,
        ) as error:
            raise LLMInvalidResponseError(
                "Gemini returned invalid structured output"
            ) from error

    @staticmethod
    def _raise_provider_error(error: Exception) -> None:
        """Translate Gemini SDK failures into the provider-neutral contract."""

        status = getattr(error, "status_code", None)
        if status is None:
            status = getattr(error, "code", None)
        if status == 429:
            raise LLMRateLimitError("Gemini rate limit exceeded") from error
        if status in {408, 504}:
            raise LLMTimeoutError("Gemini request timed out") from error
        if isinstance(error, (errors.ClientError, errors.ServerError, errors.APIError)):
            raise LLMProviderError("Gemini provider request failed") from error
        raise LLMProviderError("Gemini provider request failed") from error
