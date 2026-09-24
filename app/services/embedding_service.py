"""Application workflows for document and query embeddings."""

import math

from app.embeddings.client import EmbeddingClient, EmbeddingError, EmbeddingInputType


class EmbeddingService:
    """Embed chunks and retrieval queries through an injected model."""

    def __init__(self, embedding_client: EmbeddingClient) -> None:
        self._client = embedding_client

    async def embed_documents(self, chunks: list[str]) -> list[list[float]]:
        """Return one vector per chunk in input order; empty input returns []."""

        if not chunks:
            return []
        if any(not chunk.strip() for chunk in chunks):
            raise ValueError("Document chunks must not be empty or whitespace-only")
        vectors = await self._client.embed(chunks, input_type=EmbeddingInputType.DOCUMENT)
        self._validate_vectors(vectors, expected_count=len(chunks))
        return vectors

    async def embed_query(self, query: str) -> list[float]:
        """Return a single vector for a nonempty retrieval query."""

        if not query.strip():
            raise ValueError("Query must not be empty or whitespace-only")
        vectors = await self._client.embed([query], input_type=EmbeddingInputType.QUERY)
        self._validate_vectors(vectors, expected_count=1)
        return vectors[0]

    @staticmethod
    def _validate_vectors(vectors: list[list[float]], *, expected_count: int) -> None:
        if len(vectors) != expected_count:
            raise EmbeddingError("Expected one embedding per input text")
        dimension = len(vectors[0])
        for vector in vectors:
            if (
                not vector
                or len(vector) != dimension
                or not all(math.isfinite(value) for value in vector)
                or not any(value != 0 for value in vector)
            ):
                raise EmbeddingError("Expected finite, nonzero embeddings of equal dimension")
