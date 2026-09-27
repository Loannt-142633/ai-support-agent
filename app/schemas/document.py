"""Document API schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.document import DocumentStatus


class DocumentResponse(BaseModel):
    """Serialized uploaded document metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    document_type: str
    storage_path: str
    uploaded_at: datetime
    uploaded_by: UUID | None
    embedding_model: str
    embedding_dimension: int


class DocumentStatusResponse(BaseModel):
    """Current ingestion outcome for one uploaded document."""

    document_id: UUID
    status: DocumentStatus
    failure_reason: str | None
