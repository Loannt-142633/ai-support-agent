"""Text chunking with sentence, word, and character size fallbacks."""

import re


class ChunkingService:
    """Group paragraphs and sentences within a strict character limit."""

    # Sentence detection is punctuation-based; abbreviations may need a richer tokenizer.
    _boundary = re.compile(r'\n[ \t]*\n+|(?<=[.!?])\s+|(?<=[.!?]["”’])\s+')

    def __init__(self, max_chunk_size: int) -> None:
        if max_chunk_size <= 0:
            raise ValueError("max_chunk_size must be greater than zero")
        self._max_chunk_size = max_chunk_size

    def chunk(self, raw_text: str) -> list[str]:
        """Return ordered, nonempty chunks with separators counted toward the limit."""

        units = self._units(raw_text)
        if not units:
            return []
        if len(units) == 1:
            return [units[0][0]]

        chunks: list[str] = []
        current = units[0][0]
        for text, separator in units[1:]:
            candidate = current + separator + text
            if len(candidate) > self._max_chunk_size:
                chunks.append(current)
                current = text
            else:
                current = candidate
        chunks.append(current)
        return chunks

    def _units(self, raw_text: str) -> list[tuple[str, str]]:
        normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n").strip()
        normalized = re.sub(r"[^\S\n]+", " ", normalized)
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
        # Split only oversized sentences before grouping them into bounded chunks.
        parts = self._split_oversized(sentence)
        units.extend((part, separator if index == 0 else " ") for index, part in enumerate(parts))

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
