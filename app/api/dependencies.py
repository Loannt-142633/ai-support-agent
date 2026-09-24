"""FastAPI dependency providers for application services."""

from pathlib import Path
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.llm.client import LLMClient
from app.llm.providers.gemini import GeminiLLMClient
from app.parsers.document import DocumentParser
from app.parsers.pdf import PDFDocumentParser
from app.repositories.document_repository import DocumentRepository
from app.repositories.ticket_repository import TicketRepository
from app.repositories.user_repository import UserRepository
from app.services.document_ingestion_service import DocumentIngestionService
from app.services.document_service import DocumentService
from app.services.ticket_analysis_service import TicketAnalysisService
from app.services.ticket_service import TicketService
from app.services.user_service import UserService
from app.storage.local import LocalDocumentStorage

DbSession = Annotated[AsyncSession, Depends(get_db)]


def get_document_parser() -> DocumentParser:
    """Build the parser used for uploaded PDF documents."""

    return PDFDocumentParser()


def get_document_ingestion_service(
    parser: Annotated[DocumentParser, Depends(get_document_parser)],
) -> DocumentIngestionService:
    """Build the document text extraction workflow."""

    settings = get_settings()
    storage = LocalDocumentStorage(Path(settings.document_storage_dir))
    return DocumentIngestionService(storage, parser)


def get_user_service(session: DbSession) -> UserService:
    """Build a user service for the current request."""

    return UserService(UserRepository(session), session)


def get_ticket_service(session: DbSession) -> TicketService:
    """Build a ticket service for the current request."""

    return TicketService(TicketRepository(session), UserRepository(session), session)


def get_document_service(session: DbSession) -> DocumentService:
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


def get_ticket_analysis_service(llm_client: LLMClientDependency) -> TicketAnalysisService:
    """Build the ticket analysis service with the configured LLM client."""

    return TicketAnalysisService(llm_client)
