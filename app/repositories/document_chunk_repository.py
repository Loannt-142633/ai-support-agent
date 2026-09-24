"""SQLAlchemy repository for document chunks."""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.document_chunk import DocumentChunk


@dataclass(frozen=True)
class DocumentChunkCreate:
    """Data required to persist one embedded document chunk."""

    document_id: UUID
    chunk_index: int
    content: str
    embedding: list[float]


@dataclass(frozen=True)
class SimilarDocumentChunk:
    """A document chunk ranked by cosine distance from a query."""

    document_id: UUID
    chunk_index: int
    content: str
    distance: float


class DocumentChunkRepository:
    """Persist document chunks in batches."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bulk_create(
        self, records: Sequence[DocumentChunkCreate]
    ) -> list[DocumentChunk]:
        """Insert all chunk records with one bulk statement."""

        if not records:
            return []
        values = [
            {
                "id": uuid4(),
                "document_id": record.document_id,
                "chunk_index": record.chunk_index,
                "content": record.content,
                "embedding": record.embedding,
            }
            for record in records
        ]
        result = await self._session.scalars(
            insert(DocumentChunk).returning(DocumentChunk), values
        )
        return list(result.all())

    async def search_similar(
        self,
        *,
        query_vector: list[float],
        top_k: int,
        document_type: str | None = None,
        max_distance: float | None = None,
    ) -> list[SimilarDocumentChunk]:
        """Filter by cosine distance, then return the nearest matching chunks."""

        if not query_vector:
            raise ValueError("query_vector must not be empty")
        if top_k <= 0:
            raise ValueError("top_k must be greater than zero")
        if max_distance is not None and not 0 <= max_distance <= 2:
            raise ValueError("max_distance must be between 0 and 2")

        distance = DocumentChunk.embedding.cosine_distance(query_vector)
        statement = select(
            DocumentChunk.document_id,
            DocumentChunk.chunk_index,
            DocumentChunk.content,
            distance.label("distance"),
        )
        if document_type is not None:
            normalized_type = document_type.strip()
            if not normalized_type:
                raise ValueError("document_type must not be empty")
            statement = statement.join(
                Document, Document.id == DocumentChunk.document_id
            ).where(Document.document_type == normalized_type)
        if max_distance is not None:
            statement = statement.where(distance <= max_distance)
        statement = statement.order_by(distance.asc()).limit(top_k)

        result = await self._session.execute(statement)
        return [
            SimilarDocumentChunk(
                document_id=document_id,
                chunk_index=chunk_index,
                content=content,
                distance=float(chunk_distance),
            )
            for document_id, chunk_index, content, chunk_distance in result.all()
        ]
