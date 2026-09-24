import asyncio
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.document_ingestion_service import (
    DocumentIngestionService,
    NoExtractableTextError,
)


def build_service() -> tuple[
    DocumentIngestionService,
    MagicMock,
    AsyncMock,
    MagicMock,
    AsyncMock,
    AsyncMock,
    AsyncMock,
]:
    storage = MagicMock()
    parser = AsyncMock()
    chunking = MagicMock()
    embedding = AsyncMock()
    repository = AsyncMock()
    session = AsyncMock()
    service = DocumentIngestionService(
        storage, parser, chunking, embedding, repository, session
    )
    return service, storage, parser, chunking, embedding, repository, session


def test_ingest_parses_chunks_embeds_and_bulk_persists_in_order() -> None:
    service, storage, parser, chunking, embedding, repository, session = build_service()
    document_id = uuid4()
    document = Document(id=document_id, storage_path="stored/document.pdf")
    source = BytesIO(b"pdf")
    storage.open.return_value.__enter__.return_value = source
    parser.parse.return_value = "  First policy\r\n\r\nSecond policy  "
    chunking.chunk.return_value = ["First policy", "Second policy"]
    embedding.embed_documents.return_value = [[1.0, 0.0], [0.0, 1.0]]
    persisted = [
        DocumentChunk(
            document_id=document_id,
            chunk_index=index,
            content=content,
            embedding=vector,
        )
        for index, (content, vector) in enumerate(
            zip(chunking.chunk.return_value, embedding.embed_documents.return_value, strict=True)
        )
    ]
    repository.bulk_create.return_value = persisted

    result = asyncio.run(service.ingest(document))

    assert result == persisted
    storage.open.assert_called_once_with("stored/document.pdf")
    parser.parse.assert_awaited_once_with(source)
    chunking.chunk.assert_called_once_with("First policy\n\nSecond policy")
    embedding.embed_documents.assert_awaited_once_with(["First policy", "Second policy"])
    records = repository.bulk_create.await_args.args[0]
    assert [(record.chunk_index, record.content, record.embedding) for record in records] == [
        (0, "First policy", [1.0, 0.0]),
        (1, "Second policy", [0.0, 1.0]),
    ]
    assert all(record.document_id == document_id for record in records)
    repository.bulk_create.assert_awaited_once()
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()
    storage.open.return_value.__exit__.assert_called_once()


def test_ingest_rejects_documents_without_extractable_text() -> None:
    service, storage, parser, chunking, embedding, repository, session = build_service()
    storage.open.return_value.__enter__.return_value = BytesIO(b"pdf")
    parser.parse.return_value = " \r\n\t "
    document = Document(id=uuid4(), storage_path="stored/empty.pdf")

    with pytest.raises(NoExtractableTextError, match="no extractable text"):
        asyncio.run(service.ingest(document))

    chunking.chunk.assert_not_called()
    embedding.embed_documents.assert_not_awaited()
    repository.bulk_create.assert_not_awaited()
    session.commit.assert_not_awaited()


def test_ingest_rolls_back_when_bulk_persistence_fails() -> None:
    service, storage, parser, chunking, embedding, repository, session = build_service()
    storage.open.return_value.__enter__.return_value = BytesIO(b"pdf")
    parser.parse.return_value = "Policy"
    chunking.chunk.return_value = ["Policy"]
    embedding.embed_documents.return_value = [[1.0]]
    repository.bulk_create.side_effect = RuntimeError("database unavailable")
    document = Document(id=uuid4(), storage_path="stored/document.pdf")

    with pytest.raises(RuntimeError, match="database unavailable"):
        asyncio.run(service.ingest(document))

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


def test_ingest_requires_a_persisted_document() -> None:
    service, storage, _, _, _, _, _ = build_service()

    with pytest.raises(ValueError, match="persisted"):
        asyncio.run(service.ingest(Document(storage_path="stored/document.pdf")))

    storage.open.assert_not_called()
