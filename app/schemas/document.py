"""Document API schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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
