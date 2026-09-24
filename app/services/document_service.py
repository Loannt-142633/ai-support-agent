"""Document upload application service."""

from pathlib import Path
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.repositories.document_repository import DocumentRepository


class DocumentStorage(Protocol):
    """Storage operations required by the document upload workflow."""

    async def save(self, *, filename: str, content: bytes) -> str: ...

    async def delete(self, storage_path: str) -> None: ...


class InvalidDocumentError(ValueError):
    """Raised when an uploaded document violates the upload contract."""


class DocumentService:
    """Validate, store, and persist uploaded documents."""

    def __init__(
        self,
        repository: DocumentRepository,
        storage: DocumentStorage,
        session: AsyncSession,
        *,
        embedding_model: str,
        embedding_dimension: int,
        max_file_size: int,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._session = session
        self._embedding_model = embedding_model
        self._embedding_dimension = embedding_dimension
        self._max_file_size = max_file_size

    @property
    def max_file_size(self) -> int:
        """Maximum accepted upload size in bytes."""

        return self._max_file_size

    async def upload(
        self,
        *,
        filename: str,
        content_type: str | None,
        content: bytes,
        document_type: str,
    ) -> Document:
        """Validate a PDF, save it, and record its metadata."""

        normalized_type = document_type.strip()
        self._validate(
            filename=filename,
            content_type=content_type,
            content=content,
            document_type=normalized_type,
        )

        storage_path = await self._storage.save(filename=filename, content=content)
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

    def _validate(
        self,
        *,
        filename: str,
        content_type: str | None,
        content: bytes,
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
        if not content:
            raise InvalidDocumentError("The uploaded file is empty")
        if len(content) > self._max_file_size:
            raise InvalidDocumentError(
                f"The uploaded file exceeds the {self._max_file_size}-byte limit"
            )
        if not content.startswith(b"%PDF-"):
            raise InvalidDocumentError("The uploaded file is not a valid PDF")
