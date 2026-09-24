"""SQLAlchemy repository for document chunks."""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_chunk import DocumentChunk


@dataclass(frozen=True)
class DocumentChunkCreate:
    """Data required to persist one embedded document chunk."""

    document_id: UUID
    chunk_index: int
    content: str
    embedding: list[float]


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
