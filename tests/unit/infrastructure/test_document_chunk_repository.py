import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from app.models.document_chunk import DocumentChunk
from app.repositories.document_chunk_repository import (
    DocumentChunkCreate,
    DocumentChunkRepository,
    SimilarDocumentChunk,
)
from sqlalchemy.sql.dml import Insert


def test_bulk_create_executes_one_insert_for_all_records() -> None:
    session = AsyncMock()
    scalar_result = MagicMock()
    persisted = [MagicMock(spec=DocumentChunk), MagicMock(spec=DocumentChunk)]
    scalar_result.all.return_value = persisted
    session.scalars.return_value = scalar_result
    document_id = uuid4()
    records = [
        DocumentChunkCreate(document_id, 0, "First", [1.0, 0.0]),
        DocumentChunkCreate(document_id, 1, "Second", [0.0, 1.0]),
    ]

    result = asyncio.run(DocumentChunkRepository(session).bulk_create(records))

    assert result == persisted
    session.scalars.assert_awaited_once()
    statement, values = session.scalars.await_args.args
    assert isinstance(statement, Insert)
    assert len(values) == 2
    assert [value["chunk_index"] for value in values] == [0, 1]
    assert [value["content"] for value in values] == ["First", "Second"]


def test_bulk_create_skips_database_for_empty_batch() -> None:
    session = AsyncMock()

    assert asyncio.run(DocumentChunkRepository(session).bulk_create([])) == []
    session.scalars.assert_not_awaited()


def test_search_similar_filters_document_type_and_maps_ranked_results() -> None:
    session = AsyncMock()
    document_id = uuid4()
    query_result = MagicMock()
    query_result.all.return_value = [(document_id, 2, "Closest policy", 0.125)]
    session.execute.return_value = query_result

    result = asyncio.run(
        DocumentChunkRepository(session).search_similar(
            query_vector=[1.0, 0.0],
            top_k=3,
            document_type=" refund_policy ",
        )
    )

    assert result == [SimilarDocumentChunk(document_id, 2, "Closest policy", 0.125)]
    session.execute.assert_awaited_once()
    sql = str(session.execute.await_args.args[0])
    assert "JOIN documents" in sql
    assert "documents.document_type" in sql
    assert "ORDER BY" in sql
    assert "LIMIT" in sql


def test_search_similar_does_not_join_documents_without_filter() -> None:
    session = AsyncMock()
    query_result = MagicMock()
    query_result.all.return_value = []
    session.execute.return_value = query_result

    result = asyncio.run(
        DocumentChunkRepository(session).search_similar(
            query_vector=[1.0, 0.0], top_k=5
        )
    )

    assert result == []
    assert "JOIN documents" not in str(session.execute.await_args.args[0])


def test_search_similar_filters_distance_in_sql_before_limit() -> None:
    session = AsyncMock()
    query_result = MagicMock()
    query_result.all.return_value = []
    session.execute.return_value = query_result

    result = asyncio.run(
        DocumentChunkRepository(session).search_similar(
            query_vector=[1.0, 0.0], top_k=3, max_distance=0.24
        )
    )

    assert result == []
    statement = session.execute.await_args.args[0]
    sql = str(statement)
    assert "WHERE" in sql
    assert "<=>" in sql
    assert sql.index("WHERE") < sql.index("ORDER BY") < sql.index("LIMIT")
    assert 0.24 in statement.compile().params.values()


@pytest.mark.parametrize("max_distance", [-0.1, 2.1])
def test_search_similar_rejects_invalid_max_distance(max_distance: float) -> None:
    session = AsyncMock()

    with pytest.raises(ValueError, match="max_distance"):
        asyncio.run(
            DocumentChunkRepository(session).search_similar(
                query_vector=[1.0], top_k=3, max_distance=max_distance
            )
        )

    session.execute.assert_not_awaited()


@pytest.mark.parametrize(
    ("query_vector", "top_k", "document_type"),
    [([], 1, None), ([1.0], 0, None), ([1.0], 1, "  ")],
)
def test_search_similar_rejects_invalid_input(
    query_vector: list[float], top_k: int, document_type: str | None
) -> None:
    session = AsyncMock()

    with pytest.raises(ValueError):
        asyncio.run(
            DocumentChunkRepository(session).search_similar(
                query_vector=query_vector,
                top_k=top_k,
                document_type=document_type,
            )
        )

    session.execute.assert_not_awaited()
