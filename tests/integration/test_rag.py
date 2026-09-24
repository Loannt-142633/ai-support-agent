"""End-to-end RAG test using the sample policy and live providers."""

import asyncio
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

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
from sqlalchemy.ext.asyncio import AsyncSession

POLICY_PDF = (
    Path(__file__).resolve().parents[2]
    / "uploads"
    / "documents"
    / "2903f322f86044bfa606a5f9947b77a3.pdf"
)
HF_TEST_CACHE = Path(__file__).resolve().parents[2] / ".venv" / "huggingface"
QUESTION = "Can I get a refund for a $600 order?"


@pytest.mark.integration
def test_policy_pdf_answers_question_with_real_retrieval_and_gemini(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Parse and index a PDF, retrieve Top-3, then send their context to Gemini."""

    assert POLICY_PDF.is_file(), f"Missing integration fixture: {POLICY_PDF}"
    settings = get_settings()
    if not settings.gemini_api_key.strip():
        pytest.skip("GEMINI_API_KEY is not configured")

    monkeypatch.setenv("HF_HOME", str(HF_TEST_CACHE))
    asyncio.run(_run_rag_test())


async def _run_rag_test() -> None:
    try:
        async with SessionLocal() as session:
            await _ingest_retrieve_and_answer(session)
    finally:
        await engine.dispose()


async def _ingest_retrieve_and_answer(session: AsyncSession) -> None:
    settings = get_settings()
    document_type = f"rag_integration_{uuid4().hex}"
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
        persisted = await ingestion.ingest(document)
        assert persisted

        retrieval = RetrievalService(
            embedding_service,
            chunk_repository,
            max_distance=settings.max_distance,
        )
        top_three = await retrieval.retrieve(
            QUESTION, top_k=3, document_type=document_type
        )
        assert 0 < len(top_three) <= 3
        assert all(chunk.document_id == document_id for chunk in top_three)
        assert all(chunk.distance <= settings.max_distance for chunk in top_three)
        assert [chunk.distance for chunk in top_three] == sorted(
            chunk.distance for chunk in top_three
        )
        assert any("manager approval" in chunk.content.lower() for chunk in top_three)

        gemini = GeminiLLMClient(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            timeout=settings.gemini_timeout,
        )
        with patch.object(
            gemini, "generate_structured", wraps=gemini.generate_structured
        ) as generate:
            answer = await RAGService(retrieval, gemini).answer(
                QUESTION, top_k=3, document_type=document_type
            )

        generate.assert_awaited_once()
        assert generate.await_args is not None
        prompt = generate.await_args.kwargs["prompt"]
        assert generate.await_args.kwargs["response_model"] is RAGAnswer
        assert prompt.startswith("INSTRUCTION\n\n- Answer only using the provided context.")
        assert prompt.endswith(f"QUESTION\n{QUESTION}")
        assert prompt.count("[Chunk ") == len(top_three)
        positions = []
        for index, chunk in enumerate(top_three, start=1):
            positions.append(prompt.index(f"[Chunk {index}]\n{chunk.content}"))
        assert positions == sorted(positions)

        print(f"\nQuestion: {QUESTION}")
        for rank, chunk in enumerate(top_three, start=1):
            print(f"#{rank} distance={chunk.distance:.6f}: {chunk.content}")
        print(f"\nGemini answer: {answer}")

        assert answer.strip()
        assert "manager" in answer.lower()
        assert "approval" in answer.lower()
    finally:
        await session.rollback()
        stored_document = await session.get(Document, document_id)
        if stored_document is not None:
            await session.delete(stored_document)
            await session.commit()
