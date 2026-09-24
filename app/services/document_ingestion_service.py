"""Extract text from a previously stored document."""

from app.models.document import Document
from app.parsers.document import DocumentParser
from app.services.document_service import DocumentStorage


class NoExtractableTextError(ValueError):
    """Raised when a document has no text after normalization."""


class DocumentIngestionService:
    """Read a stored document and return its normalized text."""

    def __init__(self, storage: DocumentStorage, parser: DocumentParser) -> None:
        self._storage = storage
        self._parser = parser

    async def ingest(self, document: Document) -> str:
        """Extract text from a document or report that none is available."""

        with self._storage.open(document.storage_path) as source:
            extracted_text = await self._parser.parse(source)

        text = extracted_text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            raise NoExtractableTextError("Document has no extractable text")
        return text
