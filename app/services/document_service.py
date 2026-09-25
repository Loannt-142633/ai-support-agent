"""Document upload application service."""

from collections.abc import AsyncIterator
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.parsers.document import ReadableDocument
from app.repositories.document_repository import DocumentRepository
from app.services.document_ingestion_publisher import DocumentIngestionPublisher


class DocumentStorage(Protocol):
    """Store documents and provide seekable sources for parsing."""

    async def save(self, *, filename: str, chunks: AsyncIterator[bytes]) -> str: ...

    def open(self, storage_path: str) -> AbstractContextManager[ReadableDocument]:
        """Open a stored document for reading; close it on context exit."""
        ...

    async def delete(self, storage_path: str) -> None: ...


class InvalidDocumentError(ValueError):
    """Raised when an uploaded document violates the upload contract."""


class AsyncFileStream(Protocol):
    """Framework-independent readable asynchronous file stream."""

    async def read(self, size: int = -1) -> bytes: ...


class DocumentService:
    """Validate, store, and persist uploaded documents."""

    _chunk_size = 1024 * 1024

    def __init__(
        self,
        repository: DocumentRepository,
        storage: DocumentStorage,
        session: AsyncSession,
        *,
        embedding_model: str,
        embedding_dimension: int,
        max_file_size: int,
        ingestion_publisher: DocumentIngestionPublisher | None = None,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._session = session
        self._embedding_model = embedding_model
        self._embedding_dimension = embedding_dimension
        self._max_file_size = max_file_size
        self._ingestion_publisher = ingestion_publisher

    async def upload(
        self,
        *,
        filename: str,
        content_type: str | None,
        stream: AsyncFileStream,
        document_type: str,
    ) -> Document:
        """Validate a PDF, save it, and record its metadata."""

        normalized_type = document_type.strip()
        self._validate_metadata(
            filename=filename,
            content_type=content_type,
            document_type=normalized_type,
        )

        storage_path = await self._storage.save(
            filename=filename,
            chunks=self._validated_chunks(stream),
        )
        try:
            document = await self._repository.create(
                filename=Path(filename).name,
                storage_path=storage_path,
                document_type=normalized_type,
                embedding_model=self._embedding_model,
                embedding_dimension=self._embedding_dimension,
            )
            await self._session.commit()
            await self._session.refresh(document)
            return document
        except Exception:
            await self._session.rollback()
            await self._storage.delete(storage_path)
            raise

    def _validate_metadata(
        self,
        *,
        filename: str,
        content_type: str | None,
        document_type: str,
    ) -> None:
        if not document_type:
            raise InvalidDocumentError("document_type must not be empty")
        if len(document_type) > 100:
            raise InvalidDocumentError("document_type must not exceed 100 characters")
        if not filename or Path(filename).suffix.lower() != ".pdf":
            raise InvalidDocumentError("Only PDF files are allowed")
        if content_type not in {"application/pdf", "application/octet-stream"}:
            raise InvalidDocumentError("Only PDF files are allowed")

    async def _validated_chunks(self, stream: AsyncFileStream) -> AsyncIterator[bytes]:
        total_size = 0
        first_chunk = True
        while chunk := await stream.read(self._chunk_size):
            if first_chunk:
                if not chunk.startswith(b"%PDF-"):
                    raise InvalidDocumentError("The uploaded file is not a valid PDF")
                first_chunk = False
            total_size += len(chunk)
            if total_size > self._max_file_size:
                raise InvalidDocumentError(
                    f"The uploaded file exceeds the {self._max_file_size}-byte limit"
                )
            yield chunk
        if first_chunk:
            raise InvalidDocumentError("The uploaded file is empty")
