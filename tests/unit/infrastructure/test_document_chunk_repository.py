import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.models.document_chunk import DocumentChunk
from app.repositories.document_chunk_repository import (
    DocumentChunkCreate,
    DocumentChunkRepository,
)
from sqlalchemy.sql.dml import Insert


def test_bulk_create_executes_one_insert_for_all_records() -> None:
    session = AsyncMock()
    scalar_result = MagicMock()
    persisted = [MagicMock(spec=DocumentChunk), MagicMock(spec=DocumentChunk)]
    scalar_result.all.return_value = persisted
    session.scalars.return_value = scalar_result
    document_id = uuid4()
    records = [
        DocumentChunkCreate(document_id, 0, "First", [1.0, 0.0]),
        DocumentChunkCreate(document_id, 1, "Second", [0.0, 1.0]),
    ]

    result = asyncio.run(DocumentChunkRepository(session).bulk_create(records))

    assert result == persisted
    session.scalars.assert_awaited_once()
    statement, values = session.scalars.await_args.args
    assert isinstance(statement, Insert)
    assert len(values) == 2
    assert [value["chunk_index"] for value in values] == [0, 1]
    assert [value["content"] for value in values] == ["First", "Second"]


def test_bulk_create_skips_database_for_empty_batch() -> None:
    session = AsyncMock()

    assert asyncio.run(DocumentChunkRepository(session).bulk_create([])) == []
    session.scalars.assert_not_awaited()
