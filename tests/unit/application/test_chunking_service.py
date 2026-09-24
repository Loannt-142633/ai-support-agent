import asyncio
from unittest.mock import AsyncMock

import pytest
from app.embeddings.client import EmbeddingError
from app.services.chunking_service import ChunkingService


class SimilarEmbeddings:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


def chunk(text: str, size: int = 500) -> list[str]:
    return asyncio.run(ChunkingService(size, SimilarEmbeddings()).chunk(text))


def test_similar_sentences_stay_together_but_topic_change_starts_new_chunk() -> None:
    embeddings = AsyncMock()
    embeddings.embed.return_value = [[2.0, 0.0], [3.0, 0.0], [0.0, 4.0]]
    service = ChunkingService(500, embeddings)
    text = "Refunds are available. Return your receipt. Delivery is free."

    result = asyncio.run(service.chunk(text))

    assert result == ["Refunds are available. Return your receipt.", "Delivery is free."]
    embeddings.embed.assert_awaited_once_with(
        ["Refunds are available.", "Return your receipt.", "Delivery is free."]
    )


def test_size_fallback_preserves_whole_sentences() -> None:
    assert chunk("Hello there. Welcome back.", 20) == ["Hello there.", "Welcome back."]


def test_similar_paragraphs_group_with_blank_line_preserved() -> None:
    assert chunk("  First  \r\n \r\n\nSecond\n\nThird", 16) == ["First\n\nSecond", "Third"]


def test_long_sentence_falls_back_to_words() -> None:
    assert chunk("hello world again", 10) == ["hello", "world", "again"]


def test_word_ending_exactly_at_limit_is_preserved() -> None:
    assert chunk("hello world again", 11) == ["hello world", "again"]


def test_long_word_falls_back_to_characters_without_losing_content() -> None:
    text = "x" * 800
    result = chunk(text, 500)
    assert [len(part) for part in result] == [500, 300]
    assert "".join(result) == text


def test_one_character_limit_never_emits_blank_chunks() -> None:
    assert chunk("a b", 1) == ["a", "b"]


@pytest.mark.parametrize("text", ["", " \n\n\t "])
def test_empty_input_skips_embedding(text: str) -> None:
    embeddings = AsyncMock()
    assert asyncio.run(ChunkingService(500, embeddings).chunk(text)) == []
    embeddings.embed.assert_not_awaited()


def test_single_short_sentence_skips_embedding() -> None:
    embeddings = AsyncMock()
    result = asyncio.run(ChunkingService(500, embeddings).chunk("One sentence."))
    assert result == ["One sentence."]
    embeddings.embed.assert_not_awaited()


@pytest.mark.parametrize("size", [0, -1])
def test_rejects_nonpositive_size(size: int) -> None:
    with pytest.raises(ValueError, match="max_chunk_size"):
        ChunkingService(size, SimilarEmbeddings())


@pytest.mark.parametrize("threshold", [-1.1, 1.1, float("nan")])
def test_rejects_invalid_similarity_threshold(threshold: float) -> None:
    with pytest.raises(ValueError, match="similarity_threshold"):
        ChunkingService(500, SimilarEmbeddings(), similarity_threshold=threshold)


@pytest.mark.parametrize(
    "vectors",
    [[], [[1.0]], [[1.0], [1.0, 2.0]], [[0.0], [1.0]], [[float("nan")], [1.0]]],
)
def test_rejects_unusable_embeddings(vectors: list[list[float]]) -> None:
    embeddings = AsyncMock()
    embeddings.embed.return_value = vectors
    with pytest.raises(EmbeddingError):
        asyncio.run(ChunkingService(500, embeddings).chunk("First. Second."))


def test_embedding_failure_is_not_silently_treated_as_semantic_chunking() -> None:
    embeddings = AsyncMock()
    embeddings.embed.side_effect = EmbeddingError("unavailable")
    with pytest.raises(EmbeddingError, match="unavailable"):
        asyncio.run(ChunkingService(500, embeddings).chunk("First. Second."))


def test_fallback_preserves_order_and_all_nonwhitespace_content() -> None:
    text = "Chính sách hoàn tiền.\n\n" + "Một câu rất dài " * 40 + "x" * 600
    result = chunk(text, 50)
    assert all(part.strip() and len(part) <= 50 for part in result)
    assert "".join("".join(result).split()) == "".join(text.split())


def test_closing_quote_and_decimal_are_kept_in_sentences() -> None:
    embeddings = AsyncMock()
    embeddings.embed.return_value = [[1.0], [1.0]]
    asyncio.run(ChunkingService(500, embeddings).chunk('Price is 3.14. "Thank you!"'))
    embeddings.embed.assert_awaited_once_with(["Price is 3.14.", '"Thank you!"'])
