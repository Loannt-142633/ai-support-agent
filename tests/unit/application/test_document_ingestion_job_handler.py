import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from app.jobs.document_ingestion_handler import (
    DocumentIngestionJobHandler,
    DocumentNotFoundError,
)
from app.models.document import Document, DocumentStatus


def build_handler() -> tuple[DocumentIngestionJobHandler, MagicMock, AsyncMock]:
    session = AsyncMock()
    context = AsyncMock()
    context.__aenter__.return_value = session
    session_factory = MagicMock(return_value=context)
    handler = DocumentIngestionJobHandler(
        session_factory,
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )
    return handler, session_factory, session


@pytest.mark.parametrize(
    "starting_status",
    [DocumentStatus.PENDING, DocumentStatus.PROCESSING, DocumentStatus.FAILED],
)
def test_handle_uses_one_session_to_find_and_ingest_document(
    starting_status: DocumentStatus,
) -> None:
    handler, session_factory, session = build_handler()
    document_id = uuid4()
    document = Document(
        id=document_id,
        status=starting_status.value,
        failure_reason="previous failure" if starting_status is DocumentStatus.FAILED else None,
    )

    async def ingest(received_document: Document) -> None:
        assert received_document is document
        assert document.status == DocumentStatus.PROCESSING.value
        assert document.failure_reason is None

    with (
        patch("app.jobs.document_ingestion_handler.DocumentRepository") as documents,
        patch("app.jobs.document_ingestion_handler.DocumentChunkRepository") as chunks,
        patch("app.jobs.document_ingestion_handler.DocumentIngestionService") as ingestion,
    ):
        documents.return_value.get_by_id = AsyncMock(return_value=document)
        chunks.return_value.has_chunks = AsyncMock(return_value=False)
        ingestion.return_value.ingest = AsyncMock(side_effect=ingest)
        asyncio.run(handler.handle(document_id))

    session_factory.assert_called_once_with()
    documents.assert_called_once_with(session)
    documents.return_value.get_by_id.assert_awaited_once_with(document_id)
    chunks.assert_called_once_with(session)
    chunks.return_value.has_chunks.assert_awaited_once_with(document_id)
    assert ingestion.call_args.args[-2] is chunks.return_value
    assert ingestion.call_args.args[-1] is session
    ingestion.return_value.ingest.assert_awaited_once_with(document)
    assert document.status == DocumentStatus.COMPLETED.value
    assert document.failure_reason is None
    assert session.commit.await_count == 2
    session_factory.return_value.__aexit__.assert_awaited_once()


def test_handle_skips_ingestion_when_document_already_has_chunks() -> None:
    handler, session_factory, session = build_handler()
    document_id = uuid4()
    document = Document(
        id=document_id,
        status=DocumentStatus.PROCESSING.value,
        failure_reason="stale failure",
    )

    with (
        patch("app.jobs.document_ingestion_handler.DocumentRepository") as documents,
        patch("app.jobs.document_ingestion_handler.DocumentChunkRepository") as chunks,
        patch("app.jobs.document_ingestion_handler.DocumentIngestionService") as ingestion,
    ):
        documents.return_value.get_by_id = AsyncMock(return_value=document)
        chunks.return_value.has_chunks = AsyncMock(return_value=True)
        asyncio.run(handler.handle(document_id))

    documents.return_value.get_by_id.assert_awaited_once_with(document_id)
    chunks.assert_called_once_with(session)
    chunks.return_value.has_chunks.assert_awaited_once_with(document_id)
    ingestion.assert_not_called()
    assert document.status == DocumentStatus.COMPLETED.value
    assert document.failure_reason is None
    session.commit.assert_awaited_once_with()
    session_factory.return_value.__aexit__.assert_awaited_once()


@pytest.mark.parametrize("has_chunks", [False, True])
def test_mark_failed_records_reason_or_recovers_committed_chunks(has_chunks: bool) -> None:
    handler, session_factory, session = build_handler()
    document_id = uuid4()
    document = Document(id=document_id, status=DocumentStatus.PROCESSING.value)

    with (
        patch("app.jobs.document_ingestion_handler.DocumentRepository") as documents,
        patch("app.jobs.document_ingestion_handler.DocumentChunkRepository") as chunks,
    ):
        documents.return_value.get_by_id = AsyncMock(return_value=document)
        chunks.return_value.has_chunks = AsyncMock(return_value=has_chunks)
        status = asyncio.run(handler.mark_failed(document_id, "failure " * 50))

    expected = DocumentStatus.COMPLETED if has_chunks else DocumentStatus.FAILED
    assert status is expected
    assert document.status == expected.value
    if has_chunks:
        assert document.failure_reason is None
    else:
        assert document.failure_reason is not None
        assert len(document.failure_reason) == 255
    chunks.return_value.has_chunks.assert_awaited_once_with(document_id)
    session.commit.assert_awaited_once_with()
    session_factory.return_value.__aexit__.assert_awaited_once()


def test_handle_raises_when_document_does_not_exist_and_closes_session() -> None:
    handler, session_factory, session = build_handler()
    document_id = uuid4()

    with (
        patch("app.jobs.document_ingestion_handler.DocumentRepository") as documents,
        patch("app.jobs.document_ingestion_handler.DocumentChunkRepository") as chunks,
        patch("app.jobs.document_ingestion_handler.DocumentIngestionService") as ingestion,
    ):
        documents.return_value.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(DocumentNotFoundError, match=str(document_id)) as error:
            asyncio.run(handler.handle(document_id))

    assert error.value.document_id == document_id
    documents.assert_called_once_with(session)
    documents.return_value.get_by_id.assert_awaited_once_with(document_id)
    chunks.assert_not_called()
    ingestion.assert_not_called()
    session_factory.return_value.__aexit__.assert_awaited_once()
    assert session_factory.return_value.__aexit__.await_args.args[0] is DocumentNotFoundError
