"""Provider-agnostic document parser abstraction."""

from pathlib import Path
from typing import Protocol


class DocumentParser(Protocol):
    """Extract text from a stored document."""

    async def parse(self, storage_path: str | Path) -> str:
        """Return text extracted from the document at the given path."""


class DocumentParseError(Exception):
    """Raised when a stored document cannot be parsed."""


__all__ = ["DocumentParseError", "DocumentParser"]
