import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.models.document import Document
from app.repositories.document_repository import DocumentRepository


@pytest.mark.parametrize("found", [True, False])
def test_get_by_id_returns_document_or_none(found: bool) -> None:
    session = AsyncMock()
    document_id = uuid4()
    document = Document(id=document_id) if found else None
    session.get.return_value = document

    result = asyncio.run(DocumentRepository(session).get_by_id(document_id))

    assert result is document
    session.get.assert_awaited_once_with(Document, document_id)
