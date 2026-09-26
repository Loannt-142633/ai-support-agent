import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.jobs.document_ingestion_handler import DocumentIngestionJobHandler
from app.models.document import Document


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


def test_handle_uses_one_session_to_find_and_ingest_document() -> None:
    handler, session_factory, session = build_handler()
    document_id = uuid4()
    document = Document(id=document_id)

    with (
        patch("app.jobs.document_ingestion_handler.DocumentRepository") as documents,
        patch("app.jobs.document_ingestion_handler.DocumentChunkRepository") as chunks,
        patch("app.jobs.document_ingestion_handler.DocumentIngestionService") as ingestion,
    ):
        documents.return_value.get_by_id = AsyncMock(return_value=document)
        ingestion.return_value.ingest = AsyncMock()
        asyncio.run(handler.handle(document_id))

    session_factory.assert_called_once_with()
    documents.assert_called_once_with(session)
    documents.return_value.get_by_id.assert_awaited_once_with(document_id)
    chunks.assert_called_once_with(session)
    assert ingestion.call_args.args[-2] is chunks.return_value
    assert ingestion.call_args.args[-1] is session
    ingestion.return_value.ingest.assert_awaited_once_with(document)
    session_factory.return_value.__aexit__.assert_awaited_once()


def test_handle_skips_ingestion_when_document_does_not_exist() -> None:
    handler, session_factory, session = build_handler()
    document_id = uuid4()

    with (
        patch("app.jobs.document_ingestion_handler.DocumentRepository") as documents,
        patch("app.jobs.document_ingestion_handler.DocumentIngestionService") as ingestion,
    ):
        documents.return_value.get_by_id = AsyncMock(return_value=None)
        asyncio.run(handler.handle(document_id))

    documents.assert_called_once_with(session)
    documents.return_value.get_by_id.assert_awaited_once_with(document_id)
    ingestion.assert_not_called()
    session_factory.return_value.__aexit__.assert_awaited_once()
