"""Storage-agnostic document parser abstractions."""

from typing import Protocol


class ReadableDocument(Protocol):
    """Seekable binary input supplied by a document storage adapter."""

    def read(self, size: int = -1, /) -> bytes:
        """Read up to ``size`` bytes from the document."""

    def seek(self, offset: int, whence: int = 0, /) -> int:
        """Move the current read position."""

    def tell(self) -> int:
        """Return the current read position."""


class DocumentParser(Protocol):
    """Extract text from a stored document."""

    async def parse(self, source: ReadableDocument) -> str:
        """Return text extracted from a storage-independent binary source."""


class DocumentParseError(Exception):
    """Raised when a stored document cannot be parsed."""


__all__ = ["DocumentParseError", "DocumentParser", "ReadableDocument"]
