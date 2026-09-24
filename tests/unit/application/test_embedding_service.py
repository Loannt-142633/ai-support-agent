import asyncio
from unittest.mock import AsyncMock

import pytest
from app.embeddings.client import EmbeddingError, EmbeddingInputType
from app.services.embedding_service import EmbeddingService


def test_embeds_chunks_in_order_as_documents() -> None:
    client = AsyncMock()
    client.embed.return_value = [[1.0, 0.0], [0.0, 1.0]]
    chunks = ["Refund policy", "Shipping policy"]

    result = asyncio.run(EmbeddingService(client, 2).embed_documents(chunks))

    assert result == [[1.0, 0.0], [0.0, 1.0]]
    client.embed.assert_awaited_once_with(chunks, input_type=EmbeddingInputType.DOCUMENT)


def test_query_returns_single_vector_with_query_input_type() -> None:
    client = AsyncMock()
    client.embed.return_value = [[0.5, 0.5]]

    result = asyncio.run(EmbeddingService(client, 2).embed_query("Can I get a refund?"))

    assert result == [0.5, 0.5]
    client.embed.assert_awaited_once_with(
        ["Can I get a refund?"], input_type=EmbeddingInputType.QUERY
    )


def test_empty_chunk_list_does_not_call_model() -> None:
    client = AsyncMock()
    assert asyncio.run(EmbeddingService(client, 2).embed_documents([])) == []
    client.embed.assert_not_awaited()


@pytest.mark.parametrize("text", ["", " \n\t"])
def test_blank_text_is_rejected_before_model_call(text: str) -> None:
    client = AsyncMock()
    service = EmbeddingService(client, 2)
    with pytest.raises(ValueError):
        asyncio.run(service.embed_documents(["Valid chunk", text]))
    with pytest.raises(ValueError):
        asyncio.run(service.embed_query(text))
    client.embed.assert_not_awaited()


@pytest.mark.parametrize(
    "vectors",
    [[], [[1.0]], [[1.0], [1.0, 2.0]], [[], []], [[0.0], [1.0]],
     [[float("nan")], [1.0]], [[float("inf")], [1.0]]],
)
def test_invalid_document_vectors_raise_embedding_error(vectors: list[list[float]]) -> None:
    client = AsyncMock()
    client.embed.return_value = vectors
    with pytest.raises(EmbeddingError):
        asyncio.run(EmbeddingService(client, 2).embed_documents(["First", "Second"]))


def test_missing_query_vector_raises_embedding_error() -> None:
    client = AsyncMock()
    client.embed.return_value = []
    with pytest.raises(EmbeddingError):
        asyncio.run(EmbeddingService(client, 2).embed_query("Refund?"))


def test_model_failure_propagates() -> None:
    client = AsyncMock()
    client.embed.side_effect = EmbeddingError("Model unavailable")
    with pytest.raises(EmbeddingError, match="Model unavailable"):
        asyncio.run(EmbeddingService(client, 2).embed_documents(["Refund policy"]))


def test_rejects_vector_with_dimension_different_from_configuration() -> None:
    client = AsyncMock()
    client.embed.return_value = [[1.0, 2.0, 3.0]]

    with pytest.raises(EmbeddingError, match="dimension 2"):
        asyncio.run(EmbeddingService(client, 2).embed_query("Refund?"))


@pytest.mark.parametrize("dimension", [0, -1])
def test_rejects_nonpositive_configured_dimension(dimension: int) -> None:
    with pytest.raises(ValueError, match="expected_dimension"):
        EmbeddingService(AsyncMock(), dimension)
