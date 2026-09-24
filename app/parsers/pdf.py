"""PDF document parser implementation."""

import asyncio
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.parsers.document import DocumentParseError, DocumentParser


class PDFDocumentParser(DocumentParser):
    """Extract text from PDF files without blocking the event loop."""

    async def parse(self, storage_path: str | Path) -> str:
        """Extract and concatenate text from every PDF page."""

        path = Path(storage_path)
        try:
            return await asyncio.to_thread(self._parse_sync, path)
        except (OSError, PdfReadError, ValueError) as error:
            raise DocumentParseError(f"Could not parse PDF: {path}") from error

    @staticmethod
    def _parse_sync(storage_path: Path) -> str:
        reader = PdfReader(storage_path)
        return "\n\n".join(
            text for page in reader.pages if (text := page.extract_text())
        ).strip()


__all__ = ["PDFDocumentParser"]
