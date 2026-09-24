import asyncio
from unittest.mock import AsyncMock

import pytest
from app.models.document import Document
from app.services.document_service import DocumentService, InvalidDocumentError


def build_service(
    *, max_file_size: int = 100
) -> tuple[DocumentService, AsyncMock, AsyncMock, AsyncMock]:
    repository = AsyncMock()
    storage = AsyncMock()
    session = AsyncMock()
    service = DocumentService(
        repository,
        storage,
        session,
        embedding_model="test-embedding",
        embedding_dimension=768,
        max_file_size=max_file_size,
    )
    return service, repository, storage, session


def test_upload_stores_pdf_and_persists_metadata() -> None:
    service, repository, storage, session = build_service()
    storage.save.return_value = "uploads/documents/generated.pdf"
    repository.create.return_value = Document(
        filename="refund_policy.pdf",
        storage_path="uploads/documents/generated.pdf",
        document_type="refund_policy",
        embedding_model="test-embedding",
        embedding_dimension=768,
    )

    document = asyncio.run(
        service.upload(
            filename="refund_policy.pdf",
            content_type="application/pdf",
            content=b"%PDF-1.7 test",
            document_type="refund_policy",
        )
    )

    assert document.filename == "refund_policy.pdf"
    storage.save.assert_awaited_once()
    repository.create.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.parametrize(
    ("filename", "content_type", "content"),
    [
        ("policy.txt", "text/plain", b"plain text"),
        ("policy.pdf", "application/pdf", b""),
        ("policy.pdf", "application/pdf", b"not a pdf"),
        ("policy.pdf", "application/pdf", b"%PDF-" + b"x" * 100),
    ],
)
def test_upload_rejects_invalid_files(filename: str, content_type: str, content: bytes) -> None:
    service, _, storage, _ = build_service(max_file_size=100)

    with pytest.raises(InvalidDocumentError):
        asyncio.run(
            service.upload(
                filename=filename,
                content_type=content_type,
                content=content,
                document_type="refund_policy",
            )
        )

    storage.save.assert_not_awaited()


def test_upload_removes_stored_file_when_database_write_fails() -> None:
    service, repository, storage, session = build_service()
    storage.save.return_value = "uploads/documents/generated.pdf"
    repository.create.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        asyncio.run(
            service.upload(
                filename="refund_policy.pdf",
                content_type="application/pdf",
                content=b"%PDF-1.7 test",
                document_type="refund_policy",
            )
        )

    session.rollback.assert_awaited_once()
    storage.delete.assert_awaited_once_with("uploads/documents/generated.pdf")
