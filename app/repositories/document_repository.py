"""SQLAlchemy repository for uploaded documents."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document


class DocumentRepository:
    """Persist document metadata."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        filename: str,
        storage_path: str,
        document_type: str,
        embedding_model: str,
        embedding_dimension: int,
    ) -> Document:
        """Add document metadata to the current transaction."""

        document = Document(
            filename=filename,
            storage_path=storage_path,
            document_type=document_type,
            embedding_model=embedding_model,
            embedding_dimension=embedding_dimension,
        )
        self._session.add(document)
        await self._session.flush()
        return document
