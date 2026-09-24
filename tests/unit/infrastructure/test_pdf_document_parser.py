import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from app.parsers.document import DocumentParseError
from app.parsers.pdf import PDFDocumentParser


def test_parse_extracts_text_from_all_pdf_pages() -> None:
    first_page = MagicMock()
    first_page.extract_text.return_value = "First page"
    empty_page = MagicMock()
    empty_page.extract_text.return_value = None
    last_page = MagicMock()
    last_page.extract_text.return_value = "Last page"

    with patch("app.parsers.pdf.PdfReader") as reader:
        reader.return_value.pages = [first_page, empty_page, last_page]
        result = asyncio.run(PDFDocumentParser().parse("policy.pdf"))

    assert result == "First page\n\nLast page"
    reader.assert_called_once_with(Path("policy.pdf"))


def test_parse_maps_file_errors_to_document_parse_error() -> None:
    with (
        patch("app.parsers.pdf.PdfReader", side_effect=FileNotFoundError),
        pytest.raises(DocumentParseError, match="Could not parse PDF"),
    ):
        asyncio.run(PDFDocumentParser().parse("missing.pdf"))
