from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.api.dependencies import get_document_repository, get_document_service
from app.main import app
from app.models.document import Document, DocumentStatus


class FakeDocumentService:
    max_file_size = 1024

    async def upload(self, **values: object) -> Document:
        assert values["filename"] == "refund_policy.pdf"
        assert values["document_type"] == "refund_policy"
        return Document(
            id=uuid4(),
            filename=str(values["filename"]),
            storage_path="uploads/documents/generated.pdf",
            document_type=str(values["document_type"]),
            uploaded_at=datetime.now(UTC),
            embedding_model="test-embedding",
            embedding_dimension=768,
        )


def test_upload_document_accepts_multipart_pdf(client) -> None:
    app.dependency_overrides[get_document_service] = FakeDocumentService

    response = client.post(
        "/api/v1/documents",
        files={"file": ("refund_policy.pdf", b"%PDF-1.7 test", "application/pdf")},
        data={"document_type": "refund_policy"},
    )

    assert response.status_code == 201
    assert response.json()["filename"] == "refund_policy.pdf"
    assert response.json()["document_type"] == "refund_policy"


@pytest.mark.parametrize(
    ("status", "failure_reason"),
    [
        (DocumentStatus.PENDING, None),
        (DocumentStatus.PROCESSING, None),
        (DocumentStatus.COMPLETED, None),
        (DocumentStatus.FAILED, "PDF could not be parsed"),
    ],
)
def test_get_document_status_returns_persisted_state(
    client, status: DocumentStatus, failure_reason: str | None
) -> None:
    document_id = uuid4()
    document = Document(
        id=document_id,
        status=status.value,
        failure_reason=failure_reason,
    )

    class FakeDocumentRepository:
        async def get_by_id(self, received_id: object) -> Document:
            assert received_id == document_id
            return document

    app.dependency_overrides[get_document_repository] = FakeDocumentRepository

    response = client.get(f"/api/v1/documents/{document_id}/status")

    assert response.status_code == 200
    assert response.json() == {
        "document_id": str(document_id),
        "status": status.value,
        "failure_reason": failure_reason,
    }


def test_get_document_status_returns_404_for_unknown_document(client) -> None:
    class FakeDocumentRepository:
        async def get_by_id(self, _document_id: object) -> None:
            return None

    app.dependency_overrides[get_document_repository] = FakeDocumentRepository

    response = client.get(f"/api/v1/documents/{uuid4()}/status")

    assert response.status_code == 404
