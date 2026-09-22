"""Exception contract shared by LLM providers and application services."""


class LLMError(Exception):
    """Base exception for all LLM client failures."""


class LLMTimeoutError(LLMError):
    """The LLM provider did not respond within the allowed time."""


class LLMRateLimitError(LLMError):
    """The LLM provider rejected the request because of rate limiting."""


class LLMInvalidResponseError(LLMError):
    """The provider response was malformed or failed schema validation."""


class LLMProviderError(LLMError):
    """The LLM provider returned an otherwise unspecified provider error."""


__all__ = [
    "LLMError",
    "LLMInvalidResponseError",
    "LLMProviderError",
    "LLMRateLimitError",
    "LLMTimeoutError",
]
