"""Verify that a redelivered ingestion job does not duplicate persisted chunks."""

import asyncio
import sys
from pathlib import Path

import pytest
from app.core.config import get_settings
from app.db.session import SessionLocal, engine
from app.embeddings.client import EmbeddingInputType
from app.jobs.document_ingestion_handler import DocumentIngestionJobHandler
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.parsers.document import ReadableDocument
from app.repositories.document_repository import DocumentRepository
from app.services.chunking_service import ChunkingService
from app.services.embedding_service import EmbeddingService
from app.storage.local import LocalDocumentStorage
from sqlalchemy import func, select


class CountingParser:
    def __init__(self) -> None:
        self.calls = 0

    async def parse(self, source: ReadableDocument) -> str:
        self.calls += 1
        assert self.calls == 1, "A redelivered job must not parse the document again"
        assert source.read().startswith(b"%PDF")
        return (
            "Refunds up to USD 100 may be processed automatically. "
            "Refunds above USD 500 require manager approval."
        )


class CountingEmbeddingClient:
    def __init__(self, dimension: int) -> None:
        self.dimension = dimension
        self.calls = 0

    async def embed(self, texts: list[str], *, input_type: EmbeddingInputType) -> list[list[float]]:
        self.calls += 1
        assert self.calls == 1, "A redelivered job must not embed the document again"
        assert input_type is EmbeddingInputType.DOCUMENT
        return [[1.0] + [0.0] * (self.dimension - 1) for _ in texts]


@pytest.mark.integration
def test_handler_skips_ingestion_when_document_already_has_chunks(tmp_path: Path) -> None:
    """The first delivery persists chunks; the second delivery is a no-op."""

    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    asyncio.run(_run_twice_and_verify(tmp_path), loop_factory=loop_factory)


async def _run_twice_and_verify(tmp_path: Path) -> None:
    document_id = None
    try:
        settings = get_settings()
        stored_file = tmp_path / "policy.pdf"
        stored_file.write_bytes(b"%PDF-1.7 test document")

        async with SessionLocal() as session:
            document = await DocumentRepository(session).create(
                filename=stored_file.name,
                storage_path=str(stored_file),
                document_type="idempotency_integration_test",
                embedding_model="test-embedding",
                embedding_dimension=settings.embedding_dimension,
            )
            document_id = document.id
            await session.commit()

        parser = CountingParser()
        embedding_client = CountingEmbeddingClient(settings.embedding_dimension)
        handler = DocumentIngestionJobHandler(
            SessionLocal,
            LocalDocumentStorage(tmp_path),
            parser,
            ChunkingService(60),
            EmbeddingService(embedding_client, settings.embedding_dimension),
        )

        await handler.handle(document_id)
        async with SessionLocal() as session:
            first_count = await session.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
            )
        assert first_count is not None and first_count > 0
        assert parser.calls == 1
        assert embedding_client.calls == 1

        await handler.handle(document_id)
        async with SessionLocal() as session:
            second_count = await session.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
            )
        assert second_count == first_count
        assert parser.calls == 1
        assert embedding_client.calls == 1
    finally:
        if document_id is not None:
            async with SessionLocal() as session:
                stored_document = await session.get(Document, document_id)
                if stored_document is not None:
                    await session.delete(stored_document)
                    await session.commit()
        await engine.dispose()
