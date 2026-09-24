import asyncio
from pathlib import Path

import pytest
from app.core.config import get_settings
from app.db.session import SessionLocal, engine
from app.embeddings.e5 import E5EmbeddingModel
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.parsers.pdf import PDFDocumentParser
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.services.chunking_service import ChunkingService
from app.services.document_ingestion_service import DocumentIngestionService
from app.services.embedding_service import EmbeddingService
from app.services.retrieval_service import RetrievalService
from app.storage.local import LocalDocumentStorage
from sqlalchemy import delete, select

POLICY_PDF = (
    Path(__file__).resolve().parents[2]
    / "uploads"
    / "documents"
    / "2903f322f86044bfa606a5f9947b77a3.pdf"
)
HF_TEST_CACHE = Path(__file__).resolve().parents[2] / ".venv" / "huggingface"
TEST_DOCUMENT_TYPE = "refund_policy_integration_test"


@pytest.mark.integration
def test_ingests_policy_pdf_into_postgres_with_real_e5_embeddings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ingest the policy PDF, then embed a question and inspect the Top-3."""

    assert POLICY_PDF.is_file(), f"Missing integration fixture: {POLICY_PDF}"
    monkeypatch.setenv("HF_HOME", str(HF_TEST_CACHE))
    asyncio.run(_run_with_engine_cleanup())


async def _run_with_engine_cleanup() -> None:
    try:
        await _ingest_and_verify_policy()
    finally:
        await engine.dispose()


async def _ingest_and_verify_policy() -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        await session.execute(
            delete(Document).where(Document.document_type == TEST_DOCUMENT_TYPE)
        )
        await session.commit()
        document = await DocumentRepository(session).create(
            filename=POLICY_PDF.name,
            storage_path=str(POLICY_PDF),
            document_type=TEST_DOCUMENT_TYPE,
            embedding_model=settings.embedding_model,
            embedding_dimension=settings.embedding_dimension,
        )
        await session.commit()
        await session.refresh(document)
        document_id = document.id

        try:
            chunk_repository = DocumentChunkRepository(session)
            embedding_service = EmbeddingService(
                E5EmbeddingModel(settings.embedding_model),
                settings.embedding_dimension,
            )
            service = DocumentIngestionService(
                LocalDocumentStorage(POLICY_PDF.parent),
                PDFDocumentParser(),
                ChunkingService(settings.max_chunk_size),
                embedding_service,
                chunk_repository,
                session,
            )

            chunks = await service.ingest(document)

            persisted = list(
                await session.scalars(
                    select(DocumentChunk)
                    .where(DocumentChunk.document_id == document_id)
                    .order_by(DocumentChunk.chunk_index)
                )
            )
            assert persisted
            assert [chunk.chunk_index for chunk in persisted] == list(range(len(persisted)))
            assert [chunk.content for chunk in persisted] == [chunk.content for chunk in chunks]
            assert all(
                len(chunk.embedding) == settings.embedding_dimension for chunk in persisted
            )
            assert "Refund and Reimbursement Policy" in persisted[0].content

            matches = await chunk_repository.search_similar(
                query_vector=list(persisted[0].embedding),
                top_k=1,
                document_type=TEST_DOCUMENT_TYPE,
            )
            assert len(matches) == 1
            assert matches[0].document_id == document_id
            assert matches[0].chunk_index == persisted[0].chunk_index
            assert matches[0].content == persisted[0].content
            assert abs(matches[0].distance) < 1e-5

            question = "Can I get a refund for a $600 order?"
            top_three = await RetrievalService(
                embedding_service, chunk_repository
            ).retrieve(question, top_k=3)

            print(f"\nQuestion: {question}")
            for rank, match in enumerate(top_three, start=1):
                print(
                    f"\n#{rank} distance={match.distance:.6f} "
                    f"document_id={match.document_id} chunk_index={match.chunk_index}"
                )
                print(match.content)

            assert len(top_three) == 3
            assert [match.distance for match in top_three] == sorted(
                match.distance for match in top_three
            )
            assert any(
                "manager approval" in match.content.lower() for match in top_three
            )
        finally:
            await session.rollback()
            stored_document = await session.get(Document, document_id)
            if stored_document is not None:
                await session.delete(stored_document)
                await session.commit()
