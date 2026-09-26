"""Handle a document ingestion job without depending on a message broker."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.parsers.document import DocumentParser
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.services.chunking_service import ChunkingService
from app.services.document_ingestion_service import DocumentIngestionService
from app.services.document_service import DocumentStorage
from app.services.embedding_service import EmbeddingService


class DocumentNotFoundError(LookupError):
    """Raised when an ingestion job references a missing document."""

    def __init__(self, document_id: UUID) -> None:
        self.document_id = document_id
        super().__init__(f"Document {document_id} not found")


class DocumentIngestionJobHandler:
    """Load and ingest one persisted document within a job-scoped session."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        storage: DocumentStorage,
        parser: DocumentParser,
        chunking: ChunkingService,
        embedding: EmbeddingService,
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage
        self._parser = parser
        self._chunking = chunking
        self._embedding = embedding

    async def handle(self, document_id: UUID) -> None:
        """Ingest the document or raise if missing; close this job's session."""

        async with self._session_factory() as session:
            document = await DocumentRepository(session).get_by_id(document_id)
            if document is None:
                raise DocumentNotFoundError(document_id)

            ingestion = DocumentIngestionService(
                self._storage,
                self._parser,
                self._chunking,
                self._embedding,
                DocumentChunkRepository(session),
                session,
            )
            await ingestion.ingest(document)
