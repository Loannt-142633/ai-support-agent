"""Semantic retrieval application service."""

from app.repositories.document_chunk_repository import (
    DocumentChunkRepository,
    SimilarDocumentChunk,
)
from app.services.embedding_service import EmbeddingService


class RetrievalService:
    """Embed a question and retrieve the nearest document chunks."""

    def __init__(
        self,
        embedding: EmbeddingService,
        chunk_repository: DocumentChunkRepository,
        max_distance: float,
    ) -> None:
        if not 0 <= max_distance <= 2:
            raise ValueError("max_distance must be between 0 and 2")
        self._embedding = embedding
        self._chunks = chunk_repository
        self._max_distance = max_distance

    async def retrieve(
        self,
        question: str,
        *,
        top_k: int = 3,
        document_type: str | None = None,
    ) -> list[SimilarDocumentChunk]:
        """Return chunks nearest to the embedded question."""

        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question must not be empty")
        if top_k <= 0:
            raise ValueError("top_k must be greater than zero")
        normalized_type = document_type.strip() if document_type is not None else None
        if document_type is not None and not normalized_type:
            raise ValueError("document_type must not be empty")

        query_vector = await self._embedding.embed_query(normalized_question)
        return await self._chunks.search_similar(
            query_vector=query_vector,
            top_k=top_k,
            document_type=normalized_type,
            max_distance=self._max_distance,
        )
