"""Semantic chunking with sentence, word, and character size fallbacks."""

import math
import re

from app.embeddings.client import EmbeddingClient, EmbeddingError


class ChunkingService:
    """Group adjacent sentences by cosine similarity within a character limit."""

    # Sentence detection is punctuation-based; abbreviations may need a richer tokenizer.
    _boundary = re.compile(r'\n[ \t]*\n+|(?<=[.!?])\s+|(?<=[.!?]["”’])\s+')

    def __init__(
        self,
        max_chunk_size: int,
        embedding_client: EmbeddingClient,
        *,
        similarity_threshold: float = 0.85,
    ) -> None:
        if max_chunk_size <= 0:
            raise ValueError("max_chunk_size must be greater than zero")
        if not -1 <= similarity_threshold <= 1:
            raise ValueError("similarity_threshold must be between -1 and 1")
        self._max_chunk_size = max_chunk_size
        self._embeddings = embedding_client
        self._similarity_threshold = similarity_threshold

    async def chunk(self, raw_text: str) -> list[str]:
        """Split at topic changes or size limits; preserve content order."""

        units = self._units(raw_text)
        if not units:
            return []
        if len(units) == 1:
            return [units[0][0]]

        vectors = self._normalize_vectors(
            await self._embeddings.embed([text for text, _ in units]), len(units)
        )
        chunks: list[str] = []
        current = units[0][0]
        for index, (text, separator) in enumerate(units[1:], start=1):
            similarity = sum(
                left * right for left, right in zip(vectors[index - 1], vectors[index], strict=True)
            )
            candidate = current + separator + text
            if (
                similarity < self._similarity_threshold
                or len(candidate) > self._max_chunk_size
            ):
                chunks.append(current)
                current = text
            else:
                current = candidate
        chunks.append(current)
        return chunks

    def _units(self, raw_text: str) -> list[tuple[str, str]]:
        normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n").strip()
        units: list[tuple[str, str]] = []
        start = 0
        separator = ""
        for boundary in self._boundary.finditer(normalized):
            sentence = normalized[start : boundary.start()].strip()
            if sentence:
                self._append_sentence(units, sentence, separator)
            separator = "\n\n" if boundary.group().count("\n") >= 2 else " "
            start = boundary.end()
        sentence = normalized[start:].strip()
        if sentence:
            self._append_sentence(units, sentence, separator)
        return units

    def _append_sentence(
        self, units: list[tuple[str, str]], sentence: str, separator: str
    ) -> None:
        # Bound oversized inputs before embedding; also guarantee the output size limit.
        parts = self._split_oversized(sentence)
        units.extend((part, separator if index == 0 else " ") for index, part in enumerate(parts))

    @staticmethod
    def _normalize_vectors(vectors: list[list[float]], count: int) -> list[list[float]]:
        if len(vectors) != count:
            raise EmbeddingError("Expected one embedding per text unit")
        dimension = len(vectors[0])
        normalized: list[list[float]] = []
        for vector in vectors:
            norm = math.hypot(*vector)
            if len(vector) != dimension or not math.isfinite(norm) or norm == 0:
                raise EmbeddingError("Expected finite, nonzero embeddings of equal dimension")
            normalized.append([value / norm for value in vector])
        return normalized

    def _split_oversized(self, paragraph: str) -> list[str]:
        parts: list[str] = []
        remaining = paragraph
        while len(remaining) > self._max_chunk_size:
            boundary = max(
                (
                    index
                    for index in range(1, self._max_chunk_size + 1)
                    if remaining[index].isspace()
                ),
                default=0,
            )
            if boundary:
                parts.append(remaining[:boundary].rstrip())
                remaining = remaining[boundary:].lstrip()
            else:
                parts.append(remaining[: self._max_chunk_size])
                remaining = remaining[self._max_chunk_size :].lstrip()
        if remaining:
            parts.append(remaining)
        return parts
