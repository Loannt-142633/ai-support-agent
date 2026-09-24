import asyncio
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.models.document import Document
from app.services.document_ingestion_service import (
    DocumentIngestionService,
    NoExtractableTextError,
)


def test_ingest_reads_stored_document_and_normalizes_text() -> None:
    source = BytesIO(b"pdf")
    storage = MagicMock()
    storage.open.return_value.__enter__.return_value = source
    parser = AsyncMock()
    parser.parse.return_value = "  First line\r\nSecond line  "
    document = Document(storage_path="stored/document.pdf")

    text = asyncio.run(DocumentIngestionService(storage, parser).ingest(document))

    assert text == "First line\nSecond line"
    storage.open.assert_called_once_with("stored/document.pdf")
    parser.parse.assert_awaited_once_with(source)
    storage.open.return_value.__exit__.assert_called_once()


def test_ingest_rejects_documents_without_extractable_text() -> None:
    storage = MagicMock()
    parser = AsyncMock()
    parser.parse.return_value = " \r\n\t "
    document = Document(storage_path="stored/empty.pdf")

    with pytest.raises(NoExtractableTextError, match="no extractable text"):
        asyncio.run(DocumentIngestionService(storage, parser).ingest(document))

    storage.open.return_value.__exit__.assert_called_once()
