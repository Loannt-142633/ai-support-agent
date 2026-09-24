from datetime import UTC, datetime
from uuid import uuid4

from app.api.dependencies import get_document_service
from app.main import app
from app.models.document import Document


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
