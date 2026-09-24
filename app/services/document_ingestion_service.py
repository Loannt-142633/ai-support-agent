"""Extract text from a previously stored document."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.parsers.document import DocumentParser
from app.repositories.document_chunk_repository import (
    DocumentChunkCreate,
    DocumentChunkRepository,
)
from app.services.chunking_service import ChunkingService
from app.services.document_service import DocumentStorage
from app.services.embedding_service import EmbeddingService


class NoExtractableTextError(ValueError):
    """Raised when a document has no text after normalization."""


class DocumentIngestionService:
    """Parse, chunk, embed, and persist a stored document."""

    def __init__(
        self,
        storage: DocumentStorage,
        parser: DocumentParser,
        chunking: ChunkingService,
        embedding: EmbeddingService,
        chunk_repository: DocumentChunkRepository,
        session: AsyncSession,
    ) -> None:
        self._storage = storage
        self._parser = parser
        self._chunking = chunking
        self._embedding = embedding
        self._chunks = chunk_repository
        self._session = session

    async def ingest(self, document: Document) -> list[DocumentChunk]:
        """Build and persist searchable chunks for a stored document."""

        if document.id is None:
            raise ValueError("Document must be persisted before ingestion")

        with self._storage.open(document.storage_path) as source:
            extracted_text = await self._parser.parse(source)

        text = extracted_text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            raise NoExtractableTextError("Document has no extractable text")

        chunks = self._chunking.chunk(text)
        if not chunks:
            raise NoExtractableTextError("Document has no extractable text")
        vectors = await self._embedding.embed_documents(chunks)
        records = [
            DocumentChunkCreate(
                document_id=document.id,
                chunk_index=index,
                content=content,
                embedding=vector,
            )
            for index, (content, vector) in enumerate(zip(chunks, vectors, strict=True))
        ]

        try:
            persisted_chunks = await self._chunks.bulk_create(records)
            await self._session.commit()
            return persisted_chunks
        except Exception:
            await self._session.rollback()
            raise
