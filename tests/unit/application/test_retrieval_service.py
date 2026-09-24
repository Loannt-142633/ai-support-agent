import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.repositories.document_chunk_repository import SimilarDocumentChunk
from app.services.retrieval_service import RetrievalService


def test_retrieve_embeds_question_then_searches_nearest_chunks() -> None:
    embedding = AsyncMock()
    repository = AsyncMock()
    embedding.embed_query.return_value = [0.1, 0.2]
    matches = [SimilarDocumentChunk(uuid4(), 1, "Manager approval", 0.12)]
    repository.search_similar.return_value = matches

    result = asyncio.run(
        RetrievalService(embedding, repository).retrieve(
            "  Can I get a refund for a $600 order?  ",
            top_k=3,
            document_type=" refund_policy ",
        )
    )

    assert result == matches
    embedding.embed_query.assert_awaited_once_with(
        "Can I get a refund for a $600 order?"
    )
    repository.search_similar.assert_awaited_once_with(
        query_vector=[0.1, 0.2],
        top_k=3,
        document_type="refund_policy",
    )


def test_retrieve_uses_default_top_three_without_document_filter() -> None:
    embedding = AsyncMock()
    repository = AsyncMock()
    embedding.embed_query.return_value = [1.0]
    repository.search_similar.return_value = []

    result = asyncio.run(RetrievalService(embedding, repository).retrieve("Refund?"))

    assert result == []
    repository.search_similar.assert_awaited_once_with(
        query_vector=[1.0], top_k=3, document_type=None
    )


@pytest.mark.parametrize(
    ("question", "top_k", "document_type"),
    [("  ", 3, None), ("Refund?", 0, None), ("Refund?", 3, "  ")],
)
def test_retrieve_rejects_invalid_input_before_embedding(
    question: str, top_k: int, document_type: str | None
) -> None:
    embedding = AsyncMock()
    repository = AsyncMock()

    with pytest.raises(ValueError):
        asyncio.run(
            RetrievalService(embedding, repository).retrieve(
                question,
                top_k=top_k,
                document_type=document_type,
            )
        )

    embedding.embed_query.assert_not_awaited()
    repository.search_similar.assert_not_awaited()
