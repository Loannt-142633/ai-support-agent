"""PDF document parser implementation."""

import asyncio
from typing import BinaryIO, cast

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.parsers.document import DocumentParseError, DocumentParser, ReadableDocument


class PDFDocumentParser(DocumentParser):
    """Extract text from PDF files without blocking the event loop."""

    async def parse(self, source: ReadableDocument) -> str:
        """Extract and concatenate text from every PDF page."""

        try:
            return await asyncio.to_thread(self._parse_sync, source)
        except (OSError, PdfReadError, ValueError) as error:
            raise DocumentParseError("Could not parse PDF document") from error

    @staticmethod
    def _parse_sync(source: ReadableDocument) -> str:
        reader = PdfReader(cast(BinaryIO, source))
        return "\n\n".join(
            text for page in reader.pages if (text := page.extract_text())
        ).strip()


__all__ = ["PDFDocumentParser"]
