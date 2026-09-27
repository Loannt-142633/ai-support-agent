"""Ticket-to-RAG question orchestration for staff reply drafts."""

import asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from app.api.dependencies import get_suggested_answer_service
from app.models.ticket import Ticket
from app.repositories.document_chunk_repository import SimilarDocumentChunk
from app.schemas.rag import RAGAnswer
from app.services.rag_service import RAGService
from app.services.suggested_answer_service import SuggestedAnswerService


def test_generate_uses_title_and_description_as_question() -> None:
    ticket_id = uuid4()
    tickets = AsyncMock()
    tickets.get.return_value = Ticket(
        id=ticket_id,
        title="  Can I get a refund?  ",
        description="  My order was USD 600.  ",
    )
    rag = AsyncMock()
    rag.answer.return_value = "A refund above USD 500 requires manager approval."

    result = asyncio.run(SuggestedAnswerService(tickets, rag).generate(ticket_id))

    assert result == "A refund above USD 500 requires manager approval."
    tickets.get.assert_awaited_once_with(ticket_id)
    rag.answer.assert_awaited_once_with("Can I get a refund?\n\nMy order was USD 600.")


def test_generate_missing_ticket_never_calls_rag() -> None:
    ticket_id = uuid4()
    tickets = AsyncMock()
    tickets.get.return_value = None
    rag = AsyncMock()

    with pytest.raises(LookupError, match="Ticket not found"):
        asyncio.run(SuggestedAnswerService(tickets, rag).generate(ticket_id))

    rag.answer.assert_not_awaited()


def test_missing_context_does_not_initialize_llm_provider() -> None:
    ticket_id = uuid4()
    tickets = AsyncMock()
    tickets.get.return_value = Ticket(id=ticket_id, title="Unknown policy", description="Help?")
    retrieval = AsyncMock()
    retrieval.retrieve.return_value = []

    with patch("app.api.dependencies.get_llm_client", side_effect=AssertionError("LLM called")):
        result = asyncio.run(get_suggested_answer_service(tickets, retrieval).generate(ticket_id))

    assert result == RAGService.INSUFFICIENT_INFORMATION_ANSWER


def test_relevant_context_initializes_llm_only_when_needed() -> None:
    ticket_id = uuid4()
    tickets = AsyncMock()
    tickets.get.return_value = Ticket(id=ticket_id, title="Refund", description="USD 600 order")
    retrieval = AsyncMock()
    retrieval.retrieve.return_value = [
        SimilarDocumentChunk(uuid4(), 0, "Refunds above USD 500 require approval.", 0.1)
    ]
    llm = AsyncMock()
    llm.generate_structured.return_value = RAGAnswer(answer="Manager approval is required.")

    with patch("app.api.dependencies.get_llm_client", return_value=llm) as get_llm:
        result = asyncio.run(get_suggested_answer_service(tickets, retrieval).generate(ticket_id))

    assert result == "Manager approval is required."
    get_llm.assert_called_once_with()
    llm.generate_structured.assert_awaited_once()
