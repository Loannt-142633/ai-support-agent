"""FastAPI dependency providers for application services."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.embeddings.client import EmbeddingClient
from app.embeddings.e5 import E5EmbeddingModel
from app.llm.client import LLMClient
from app.llm.deferred import DeferredLLMClient
from app.llm.providers.gemini import GeminiLLMClient
from app.llm.providers.gemini_staff_agent import GeminiStaffAgentModel
from app.messaging.kafka import KafkaTicketCreatedPublisher
from app.messaging.rabbitmq import (
    RabbitMQDocumentIngestionPublisher,
    RabbitMQTicketAnalysisPublisher,
)
from app.messaging.smtp import SMTPEmailSender
from app.parsers.document import DocumentParser
from app.parsers.pdf import PDFDocumentParser
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.ticket_ai_analysis_repository import TicketAIAnalysisRepository
from app.repositories.ticket_repository import TicketRepository
from app.repositories.ticket_suggested_answer_repository import TicketSuggestedAnswerRepository
from app.repositories.user_repository import UserRepository
from app.services.agent_service import StaffAgentModel
from app.services.chunking_service import ChunkingService
from app.services.document_ingestion_publisher import DocumentIngestionPublisher
from app.services.document_ingestion_service import DocumentIngestionService
from app.services.document_service import DocumentService
from app.services.email_sender import EmailSender
from app.services.embedding_service import EmbeddingService
from app.services.rag_service import RAGService
from app.services.retrieval_service import RetrievalService
from app.services.suggested_answer_delivery_service import SuggestedAnswerDeliveryService
from app.services.suggested_answer_service import SuggestedAnswerService
from app.services.ticket_analysis_publisher import TicketAnalysisPublisher
from app.services.ticket_analysis_service import TicketAnalysisService
from app.services.ticket_created_publisher import TicketCreatedPublisher
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


def get_ticket_analysis_publisher() -> TicketAnalysisPublisher:
    """Build the RabbitMQ publisher for ticket analysis jobs."""

    settings = get_settings()
    return RabbitMQTicketAnalysisPublisher(
        url=settings.rabbitmq_url,
        queue_name=settings.ticket_analysis_queue,
    )


def get_ticket_created_publisher() -> TicketCreatedPublisher:
    """Build the Kafka publisher for committed ticket creation events."""

    settings = get_settings()
    return KafkaTicketCreatedPublisher(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        topic=settings.ticket_created_topic,
    )


def get_ticket_service(
    session: DbSession,
    publisher: Annotated[TicketAnalysisPublisher, Depends(get_ticket_analysis_publisher)],
    created_publisher: Annotated[TicketCreatedPublisher, Depends(get_ticket_created_publisher)],
) -> TicketService:
    """Build a ticket service for the current request."""

    return TicketService(
        TicketRepository(session), UserRepository(session), session, publisher, created_publisher
    )


def get_ticket_repository(session: DbSession) -> TicketRepository:
    """Build the ticket repository for read-only lookups."""

    return TicketRepository(session)


def get_ticket_ai_analysis_repository(session: DbSession) -> TicketAIAnalysisRepository:
    """Build the analysis repository for read-only lookups."""

    return TicketAIAnalysisRepository(session)


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


def get_document_repository(session: DbSession) -> DocumentRepository:
    """Build the document repository for status lookups."""

    return DocumentRepository(session)


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


def get_suggested_answer_service(
    session: DbSession,
    tickets: Annotated[TicketRepository, Depends(get_ticket_repository)],
    retrieval: Annotated[RetrievalService, Depends(get_retrieval_service)],
) -> SuggestedAnswerService:
    """Build drafting without initializing Gemini for missing tickets or empty context."""

    return SuggestedAnswerService(
        tickets,
        RAGService(retrieval, DeferredLLMClient(get_llm_client)),
        TicketSuggestedAnswerRepository(session),
        session,
    )


def get_email_sender() -> EmailSender:
    """Build SMTP transport only for the explicit send endpoint."""

    settings = get_settings()
    if not settings.smtp_host.strip() or not settings.smtp_from_email.strip():
        raise HTTPException(status_code=503, detail="SMTP delivery is not configured")
    return SMTPEmailSender(
        host=settings.smtp_host,
        port=settings.smtp_port,
        from_email=settings.smtp_from_email,
        username=settings.smtp_username,
        password=settings.smtp_password,
        starttls=settings.smtp_starttls,
        timeout=settings.smtp_timeout,
    )


def get_suggested_answer_delivery_service(
    session: DbSession,
    tickets: Annotated[TicketRepository, Depends(get_ticket_repository)],
    sender: Annotated[EmailSender, Depends(get_email_sender)],
) -> SuggestedAnswerDeliveryService:
    """Build the email delivery workflow for the current request."""

    return SuggestedAnswerDeliveryService(
        tickets, TicketSuggestedAnswerRepository(session), sender, session
    )


def get_ticket_analysis_service(llm_client: LLMClientDependency) -> TicketAnalysisService:
    """Build the ticket analysis service with the configured LLM client."""

    return TicketAnalysisService(llm_client)


@lru_cache
def get_gemini_staff_agent_model() -> StaffAgentModel:
    """Reuse one Gemini client for local staff demo requests."""
    settings = get_settings()
    return GeminiStaffAgentModel(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        timeout=settings.gemini_timeout,
    )
