"""Ticket-to-RAG question orchestration and draft persistence."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from app.api.dependencies import get_suggested_answer_service
from app.models.ticket import Ticket
from app.models.ticket_suggested_answer import TicketSuggestedAnswer
from app.repositories.document_chunk_repository import SimilarDocumentChunk
from app.schemas.rag import RAGAnswer
from app.services.rag_service import RAGResult, RAGService
from app.services.suggested_answer_service import SuggestedAnswerService


def test_generate_saves_answer_and_exact_prompt_sources() -> None:
    ticket_id = uuid4()
    tickets = AsyncMock()
    tickets.get.return_value = Ticket(
        id=ticket_id,
        title="  Can I get a refund?  ",
        description="  My order was USD 600.  ",
    )
    chunks = (
        SimilarDocumentChunk(uuid4(), 4, "Manager approval required.", 0.1),
        SimilarDocumentChunk(uuid4(), 2, "Check payment first.", 0.2),
    )
    rag = AsyncMock()
    rag.answer.return_value = RAGResult("Approval depends on eligibility.", chunks)
    drafts = AsyncMock()
    draft = TicketSuggestedAnswer(
        ticket_id=ticket_id, ai_content="Approval depends on eligibility."
    )
    drafts.create.return_value = draft
    session = AsyncMock()

    result = asyncio.run(SuggestedAnswerService(tickets, rag, drafts, session).generate(ticket_id))

    assert result is draft
    rag.answer.assert_awaited_once_with("Can I get a refund?\n\nMy order was USD 600.")
    drafts.create.assert_awaited_once_with(
        ticket_id=ticket_id, ai_content="Approval depends on eligibility.", chunks=chunks
    )
    session.commit.assert_awaited_once()


def test_generate_missing_ticket_never_calls_rag_or_saves() -> None:
    ticket_id = uuid4()
    tickets = AsyncMock()
    tickets.get.return_value = None
    rag = AsyncMock()
    drafts = AsyncMock()
    session = AsyncMock()

    with pytest.raises(LookupError, match="Ticket not found"):
        asyncio.run(SuggestedAnswerService(tickets, rag, drafts, session).generate(ticket_id))

    rag.answer.assert_not_awaited()
    drafts.create.assert_not_awaited()
    session.commit.assert_not_awaited()


def test_generate_rolls_back_failed_save() -> None:
    ticket_id = uuid4()
    tickets = AsyncMock()
    tickets.get.return_value = Ticket(id=ticket_id, title="Refund", description="USD 600")
    rag = AsyncMock()
    rag.answer.return_value = RAGResult("Answer", ())
    drafts = AsyncMock()
    drafts.create.side_effect = RuntimeError("DB unavailable")
    session = AsyncMock()

    with pytest.raises(RuntimeError, match="DB unavailable"):
        asyncio.run(SuggestedAnswerService(tickets, rag, drafts, session).generate(ticket_id))

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


def test_get_reads_draft_without_calling_rag() -> None:
    ticket_id, draft_id = uuid4(), uuid4()
    drafts = AsyncMock()
    draft = TicketSuggestedAnswer(id=draft_id, ticket_id=ticket_id, ai_content="Saved")
    drafts.get_for_ticket.return_value = draft
    rag = AsyncMock()

    result = asyncio.run(
        SuggestedAnswerService(AsyncMock(), rag, drafts, AsyncMock()).get(ticket_id, draft_id)
    )

    assert result is draft
    drafts.get_for_ticket.assert_awaited_once_with(ticket_id=ticket_id, draft_id=draft_id)
    rag.answer.assert_not_awaited()


def test_missing_context_does_not_initialize_llm_provider() -> None:
    ticket_id = uuid4()
    tickets = AsyncMock()
    tickets.get.return_value = Ticket(id=ticket_id, title="Unknown policy", description="Help?")
    retrieval = AsyncMock()
    retrieval.retrieve.return_value = []
    session = AsyncMock()
    session.add = MagicMock()

    with patch("app.api.dependencies.get_llm_client", side_effect=AssertionError("LLM called")):
        result = asyncio.run(
            get_suggested_answer_service(session, tickets, retrieval).generate(ticket_id)
        )

    assert result.ai_content == RAGService.INSUFFICIENT_INFORMATION_ANSWER
    assert result.sources == []
    session.commit.assert_awaited_once()


def test_relevant_context_initializes_llm_only_when_needed() -> None:
    ticket_id = uuid4()
    tickets = AsyncMock()
    tickets.get.return_value = Ticket(id=ticket_id, title="Refund", description="USD 600 order")
    retrieval = AsyncMock()
    source = SimilarDocumentChunk(uuid4(), 0, "Refunds above USD 500 require approval.", 0.1)
    retrieval.retrieve.return_value = [source]
    llm = AsyncMock()
    llm.generate_structured.return_value = RAGAnswer(answer="Manager approval is required.")

    session = AsyncMock()
    session.add = MagicMock()
    with patch("app.api.dependencies.get_llm_client", return_value=llm) as get_llm:
        result = asyncio.run(
            get_suggested_answer_service(session, tickets, retrieval).generate(ticket_id)
        )

    assert result.ai_content == "Manager approval is required."
    assert [(item.document_id, item.chunk_index) for item in result.sources] == [
        (source.document_id, source.chunk_index)
    ]
    get_llm.assert_called_once_with()
    llm.generate_structured.assert_awaited_once()
