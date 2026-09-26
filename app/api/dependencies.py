"""FastAPI dependency providers for application services."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.embeddings.client import EmbeddingClient
from app.embeddings.e5 import E5EmbeddingModel
from app.llm.client import LLMClient
from app.llm.providers.gemini import GeminiLLMClient
from app.messaging.rabbitmq import RabbitMQDocumentIngestionPublisher
from app.parsers.document import DocumentParser
from app.parsers.pdf import PDFDocumentParser
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.ticket_repository import TicketRepository
from app.repositories.user_repository import UserRepository
from app.services.chunking_service import ChunkingService
from app.services.document_ingestion_publisher import DocumentIngestionPublisher
from app.services.document_ingestion_service import DocumentIngestionService
from app.services.document_service import DocumentService
from app.services.embedding_service import EmbeddingService
from app.services.rag_service import RAGService
from app.services.retrieval_service import RetrievalService
from app.services.ticket_analysis_service import TicketAnalysisService
from app.services.ticket_service import TicketService
from app.services.user_service import UserService
from app.storage.local import LocalDocumentStorage

DbSession = Annotated[AsyncSession, Depends(get_db)]


@lru_cache
def get_embedding_client() -> EmbeddingClient:
    """Reuse the lazily loaded embedding model for ingestion and retrieval."""

    settings = get_settings()
    return E5EmbeddingModel(settings.embedding_model)


def get_embedding_service(
    embedding_client: Annotated[EmbeddingClient, Depends(get_embedding_client)],
) -> EmbeddingService:
    """Build the document/query embedding service using the shared model."""

    return EmbeddingService(embedding_client, get_settings().embedding_dimension)


def get_retrieval_service(
    session: DbSession,
    embedding: Annotated[EmbeddingService, Depends(get_embedding_service)],
) -> RetrievalService:
    """Build semantic retrieval for the current database session."""

    return RetrievalService(
        embedding,
        DocumentChunkRepository(session),
        max_distance=get_settings().max_distance,
    )


def get_chunking_service() -> ChunkingService:
    """Build the paragraph/sentence chunker with a strict character limit."""

    settings = get_settings()
    return ChunkingService(settings.max_chunk_size)


def get_document_parser() -> DocumentParser:
    """Build the parser used for uploaded PDF documents."""

    return PDFDocumentParser()


def get_document_ingestion_service(
    session: DbSession,
    parser: Annotated[DocumentParser, Depends(get_document_parser)],
    chunking: Annotated[ChunkingService, Depends(get_chunking_service)],
    embedding: Annotated[EmbeddingService, Depends(get_embedding_service)],
) -> DocumentIngestionService:
    """Build the complete document ingestion workflow."""

    settings = get_settings()
    storage = LocalDocumentStorage(Path(settings.document_storage_dir))
    return DocumentIngestionService(
        storage,
        parser,
        chunking,
        embedding,
        DocumentChunkRepository(session),
        session,
    )


def get_user_service(session: DbSession) -> UserService:
    """Build a user service for the current request."""

    return UserService(UserRepository(session), session)


def get_ticket_service(session: DbSession) -> TicketService:
    """Build a ticket service for the current request."""

    return TicketService(TicketRepository(session), UserRepository(session), session)


def get_document_ingestion_publisher() -> DocumentIngestionPublisher:
    """Build the RabbitMQ publisher for document ingestion jobs."""

    settings = get_settings()
    return RabbitMQDocumentIngestionPublisher(
        url=settings.rabbitmq_url,
        queue_name=settings.document_ingestion_queue,
    )


def get_document_service(
    session: DbSession,
    publisher: Annotated[DocumentIngestionPublisher, Depends(get_document_ingestion_publisher)],
) -> DocumentService:
    """Build a document upload service for the current request."""

    settings = get_settings()
    storage = LocalDocumentStorage(Path(settings.document_storage_dir))
    return DocumentService(
        DocumentRepository(session),
        storage,
        session,
        embedding_model=settings.embedding_model,
        embedding_dimension=settings.embedding_dimension,
        max_file_size=settings.max_document_size_bytes,
        ingestion_publisher=publisher,
    )


def get_llm_client() -> LLMClient:
    """Build the configured LLM provider client."""

    settings = get_settings()
    return GeminiLLMClient(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        timeout=settings.gemini_timeout,
    )


LLMClientDependency = Annotated[LLMClient, Depends(get_llm_client)]


def get_rag_service(
    retrieval: Annotated[RetrievalService, Depends(get_retrieval_service)],
    llm_client: LLMClientDependency,
) -> RAGService:
    """Build grounded question answering for the current request."""

    return RAGService(retrieval, llm_client)


def get_ticket_analysis_service(llm_client: LLMClientDependency) -> TicketAnalysisService:
    """Build the ticket analysis service with the configured LLM client."""

    return TicketAnalysisService(llm_client)
