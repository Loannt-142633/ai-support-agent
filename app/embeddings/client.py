"""Provider-independent embedding contract."""

from typing import Protocol


class EmbeddingError(Exception):
    """Embedding generation failed or returned unusable vectors."""


class EmbeddingClient(Protocol):
    """Encode texts in order for semantic similarity comparisons."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one nonzero, finite vector of equal dimension per input text."""
