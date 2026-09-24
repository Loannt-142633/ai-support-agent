import pytest
from app.services.chunking_service import ChunkingService


def test_groups_sentences_without_embedding() -> None:
    text = "Refunds are available. Return your receipt. Delivery is free."
    assert ChunkingService(500).chunk(text) == [text]


def test_size_limit_preserves_whole_sentences() -> None:
    assert ChunkingService(20).chunk("Hello there. Welcome back.") == [
        "Hello there.", "Welcome back."
    ]


def test_normalizes_whitespace_and_preserves_paragraph_separator() -> None:
    text = "  First\t  paragraph\r\n \r\nSecond  paragraph  "
    assert ChunkingService(500).chunk(text) == ["First paragraph\n\nSecond paragraph"]


def test_separators_count_toward_size_limit() -> None:
    assert ChunkingService(12).chunk("First\n\nSecond") == ["First", "Second"]
    assert ChunkingService(13).chunk("First\n\nSecond") == ["First\n\nSecond"]


def test_long_sentence_falls_back_to_words() -> None:
    assert ChunkingService(10).chunk("hello world again") == ["hello", "world", "again"]


def test_word_ending_exactly_at_limit_is_preserved() -> None:
    assert ChunkingService(11).chunk("hello world again") == ["hello world", "again"]


def test_long_word_falls_back_to_characters_without_losing_content() -> None:
    text = "x" * 800
    result = ChunkingService(500).chunk(text)
    assert [len(part) for part in result] == [500, 300]
    assert "".join(result) == text


def test_one_character_limit_never_emits_blank_chunks() -> None:
    assert ChunkingService(1).chunk("a b") == ["a", "b"]


@pytest.mark.parametrize("text", ["", " \n\n\t "])
def test_empty_input_returns_empty_list(text: str) -> None:
    assert ChunkingService(500).chunk(text) == []


@pytest.mark.parametrize("size", [0, -1])
def test_rejects_nonpositive_size(size: int) -> None:
    with pytest.raises(ValueError, match="max_chunk_size"):
        ChunkingService(size)


def test_fallback_preserves_order_and_all_nonwhitespace_content() -> None:
    text = "Chính sách hoàn tiền.\n\n" + "Một câu rất dài " * 40 + "x" * 600
    result = ChunkingService(50).chunk(text)
    assert all(part.strip() and len(part) <= 50 for part in result)
    assert "".join("".join(result).split()) == "".join(text.split())


def test_closing_quote_and_decimal_are_kept_in_sentences() -> None:
    assert ChunkingService(15).chunk('Price is 3.14. "Thank you!" Next.') == [
        "Price is 3.14.", '"Thank you!"', "Next."
    ]
