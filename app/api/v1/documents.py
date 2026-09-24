"""Document HTTP endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.api.dependencies import get_document_service
from app.schemas.document import DocumentResponse
from app.services.document_service import DocumentService, InvalidDocumentError

router = APIRouter(prefix="/documents", tags=["documents"])
DocumentServiceDependency = Annotated[DocumentService, Depends(get_document_service)]


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    service: DocumentServiceDependency,
    file: Annotated[UploadFile, File(description="PDF policy document")],
    document_type: Annotated[str, Form(min_length=1, max_length=100)],
) -> DocumentResponse:
    """Upload a PDF document and persist its metadata."""

    try:
        content = await file.read(service.max_file_size + 1)
        document = await service.upload(
            filename=file.filename or "",
            content_type=file.content_type,
            content=content,
            document_type=document_type,
        )
        return DocumentResponse.model_validate(document)
    except InvalidDocumentError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    finally:
        await file.close()
