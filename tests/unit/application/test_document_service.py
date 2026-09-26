import asyncio
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.models.document import Document
from app.services.document_service import DocumentService, InvalidDocumentError


class AsyncBytesStream:
    def __init__(self, content: bytes) -> None:
        self._content = content
        self._position = 0

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._content)
        chunk = self._content[self._position : self._position + size]
        self._position += len(chunk)
        return chunk


async def consume_chunks(*, filename: str, chunks: AsyncIterator[bytes]) -> str:
    del filename
    async for _ in chunks:
        pass
    return "uploads/documents/generated.pdf"


def build_service(
    *, max_file_size: int = 100, publisher: AsyncMock | None = None
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
        ingestion_publisher=publisher,
    )
    return service, repository, storage, session


def test_upload_stores_pdf_and_persists_metadata() -> None:
    service, repository, storage, session = build_service()
    storage.save.side_effect = consume_chunks
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
            stream=AsyncBytesStream(b"%PDF-1.7 test"),
            document_type="refund_policy",
        )
    )

    assert document.filename == "refund_policy.pdf"
    storage.save.assert_awaited_once()
    repository.create.assert_awaited_once()
    session.commit.assert_awaited_once()


def test_upload_publishes_document_id_after_commit() -> None:
    publisher = AsyncMock()
    service, repository, storage, session = build_service(publisher=publisher)
    storage.save.side_effect = consume_chunks
    document_id = uuid4()
    repository.create.return_value = Document(id=document_id)
    events: list[str] = []

    async def commit() -> None:
        events.append("commit")

    async def refresh(document: Document) -> None:
        assert document.id == document_id
        events.append("refresh")

    async def publish(published_id: object) -> None:
        assert published_id == document_id
        events.append("publish")

    session.commit.side_effect = commit
    session.refresh.side_effect = refresh
    publisher.publish.side_effect = publish

    result = asyncio.run(
        service.upload(
            filename="refund_policy.pdf",
            content_type="application/pdf",
            stream=AsyncBytesStream(b"%PDF-1.7 test"),
            document_type="refund_policy",
        )
    )

    assert result.id == document_id
    assert events == ["commit", "refresh", "publish"]
    publisher.publish.assert_awaited_once_with(document_id)


def test_publish_failure_preserves_committed_document_and_file() -> None:
    publisher = AsyncMock()
    service, repository, storage, session = build_service(publisher=publisher)
    storage.save.side_effect = consume_chunks
    document_id = uuid4()
    repository.create.return_value = Document(id=document_id)
    publisher.publish.side_effect = RuntimeError("queue unavailable")

    with pytest.raises(RuntimeError, match="queue unavailable"):
        asyncio.run(
            service.upload(
                filename="refund_policy.pdf",
                content_type="application/pdf",
                stream=AsyncBytesStream(b"%PDF-1.7 test"),
                document_type="refund_policy",
            )
        )

    session.commit.assert_awaited_once()
    publisher.publish.assert_awaited_once_with(document_id)
    session.rollback.assert_not_awaited()
    storage.delete.assert_not_awaited()


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
    service, repository, storage, _ = build_service(max_file_size=100)
    storage.save.side_effect = consume_chunks

    with pytest.raises(InvalidDocumentError):
        asyncio.run(
            service.upload(
                filename=filename,
                content_type=content_type,
                stream=AsyncBytesStream(content),
                document_type="refund_policy",
            )
        )

    repository.create.assert_not_awaited()


def test_upload_removes_stored_file_when_database_write_fails() -> None:
    service, repository, storage, session = build_service()
    storage.save.side_effect = consume_chunks
    repository.create.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        asyncio.run(
            service.upload(
                filename="refund_policy.pdf",
                content_type="application/pdf",
                stream=AsyncBytesStream(b"%PDF-1.7 test"),
                document_type="refund_policy",
            )
        )

    session.rollback.assert_awaited_once()
    storage.delete.assert_awaited_once_with("uploads/documents/generated.pdf")
