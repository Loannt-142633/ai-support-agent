"""Provider-independent embedding contract."""

from enum import Enum
from typing import Protocol


class EmbeddingInputType(Enum):
    """How input text will be used by the embedding model."""

    QUERY = "query"
    DOCUMENT = "document"


class EmbeddingError(Exception):
    """Embedding generation failed or returned unusable vectors."""


class EmbeddingClient(Protocol):
    """Encode queries or document text without exposing model-specific prefixes."""

    async def embed(
        self, texts: list[str], *, input_type: EmbeddingInputType
    ) -> list[list[float]]:
        """Return one nonzero, finite vector of equal dimension per input text."""
