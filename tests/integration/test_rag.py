"""RAG integration tests using the sample policy and live retrieval."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from app.core.config import get_settings
from app.db.session import SessionLocal, engine
from app.embeddings.e5 import E5EmbeddingModel
from app.llm.providers.gemini import GeminiLLMClient
from app.models.document import Document
from app.parsers.pdf import PDFDocumentParser
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.schemas.rag import RAGAnswer
from app.services.chunking_service import ChunkingService
from app.services.document_ingestion_service import DocumentIngestionService
from app.services.embedding_service import EmbeddingService
from app.services.rag_service import RAGService
from app.services.retrieval_service import RetrievalService
from app.storage.local import LocalDocumentStorage

POLICY_PDF = (
    Path(__file__).resolve().parents[2]
    / "uploads"
    / "documents"
    / "2903f322f86044bfa606a5f9947b77a3.pdf"
)
HF_TEST_CACHE = Path(__file__).resolve().parents[2] / ".venv" / "huggingface"
REFUND_QUESTION = "Can I get a refund for a $600 order?"
IRRELEVANT_QUESTION = "How do I cook chicken?"
REQUIRED_EVIDENCE = "above usd 500 require manager approval"


@pytest.fixture
def policy_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    assert POLICY_PDF.is_file(), f"Missing integration fixture: {POLICY_PDF}"
    monkeypatch.setenv("HF_HOME", str(HF_TEST_CACHE))


@asynccontextmanager
async def indexed_policy() -> AsyncIterator[tuple[RetrievalService, str, UUID]]:
    settings = get_settings()
    document_type = f"rag_integration_{uuid4().hex}"
    try:
        async with SessionLocal() as session:
            document = await DocumentRepository(session).create(
                filename=POLICY_PDF.name,
                storage_path=str(POLICY_PDF),
                document_type=document_type,
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
                ingestion = DocumentIngestionService(
                    LocalDocumentStorage(POLICY_PDF.parent),
                    PDFDocumentParser(),
                    ChunkingService(settings.max_chunk_size),
                    embedding_service,
                    chunk_repository,
                    session,
                )
                assert await ingestion.ingest(document)

                retrieval = RetrievalService(
                    embedding_service,
                    chunk_repository,
                    max_distance=settings.max_distance,
                )
                yield retrieval, document_type, document_id
            finally:
                await session.rollback()
                stored_document = await session.get(Document, document_id)
                if stored_document is not None:
                    await session.delete(stored_document)
                    await session.commit()
    finally:
        await engine.dispose()


@pytest.mark.integration
def test_relevant_retrieval_contains_refund_approval_evidence(policy_pdf: None) -> None:
    async def check() -> None:
        async with indexed_policy() as (retrieval, document_type, document_id):
            chunks = await retrieval.retrieve(
                REFUND_QUESTION, top_k=3, document_type=document_type
            )

            assert chunks
            assert len(chunks) <= 3
            assert all(chunk.document_id == document_id for chunk in chunks)
            assert all(chunk.distance <= get_settings().max_distance for chunk in chunks)
            assert [chunk.distance for chunk in chunks] == sorted(
                chunk.distance for chunk in chunks
            )
            assert any(REQUIRED_EVIDENCE in chunk.content.lower() for chunk in chunks)

    asyncio.run(check())


@pytest.mark.integration
def test_irrelevant_retrieval_returns_insufficient_without_calling_llm(policy_pdf: None) -> None:
    async def check() -> None:
        async with indexed_policy() as (retrieval, document_type, _):
            chunks = await retrieval.retrieve(
                IRRELEVANT_QUESTION, top_k=3, document_type=document_type
            )
            assert chunks == []

            llm = AsyncMock()
            answer = await RAGService(retrieval, llm).answer(
                IRRELEVANT_QUESTION, top_k=3, document_type=document_type
            )

            assert answer == RAGService.INSUFFICIENT_INFORMATION_ANSWER
            llm.generate_structured.assert_not_awaited()

    asyncio.run(check())


@pytest.mark.integration
def test_live_gemini_answers_with_relevant_refund_context(policy_pdf: None) -> None:
    settings = get_settings()
    if not settings.gemini_api_key.strip():
        pytest.skip("GEMINI_API_KEY is not configured")

    async def check() -> None:
        async with indexed_policy() as (retrieval, document_type, _):
            chunks = await retrieval.retrieve(
                REFUND_QUESTION, top_k=3, document_type=document_type
            )
            assert chunks
            assert any(REQUIRED_EVIDENCE in chunk.content.lower() for chunk in chunks)

            gemini = GeminiLLMClient(
                api_key=settings.gemini_api_key,
                model=settings.gemini_model,
                timeout=settings.gemini_timeout,
            )
            with patch.object(
                gemini, "generate_structured", wraps=gemini.generate_structured
            ) as generate:
                answer = await RAGService(retrieval, gemini).answer(
                    REFUND_QUESTION, top_k=3, document_type=document_type
                )

            generate.assert_awaited_once()
            assert generate.await_args is not None
            prompt = generate.await_args.kwargs["prompt"]
            assert generate.await_args.kwargs["response_model"] is RAGAnswer
            assert prompt.startswith("INSTRUCTION\n\n- Answer only using the provided context.")
            assert prompt.endswith(f"QUESTION\n{REFUND_QUESTION}")
            assert prompt.count("[Chunk ") == len(chunks)
            positions = [
                prompt.index(f"[Chunk {index}]\n{chunk.content}")
                for index, chunk in enumerate(chunks, start=1)
            ]
            assert positions == sorted(positions)
            assert answer.strip()
            assert "manager" in answer.lower()
            assert "approv" in answer.lower()

    asyncio.run(check())
