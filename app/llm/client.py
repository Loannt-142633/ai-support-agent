"""LLM boundary used by future support-answer workflows."""

from typing import Protocol


class LLMClient(Protocol):
    """Provider-agnostic contract for language model adapters."""

    def generate(self, prompt: str) -> str:
        """Generate a response for a prompt."""
