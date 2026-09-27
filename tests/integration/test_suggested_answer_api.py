"""HTTP flow for generating a grounded, unsent support reply draft."""

from unittest.mock import AsyncMock
from uuid import uuid4

from app.api.dependencies import get_suggested_answer_service
from app.main import app
from app.models.ticket import Ticket
from app.repositories.document_chunk_repository import SimilarDocumentChunk
from app.schemas.rag import RAGAnswer
from app.services.rag_service import RAGService
from app.services.suggested_answer_service import SuggestedAnswerService


def test_suggested_answer_uses_retrieved_policy_without_sending(client) -> None:
    ticket_id = uuid4()
    tickets = AsyncMock()
    tickets.get.return_value = Ticket(
        id=ticket_id,
        title="Can I get a refund?",
        description="My order was USD 600.",
    )
    retrieval = AsyncMock()
    retrieval.retrieve.return_value = [
        SimilarDocumentChunk(uuid4(), 0, "Refunds above USD 500 require manager approval.", 0.1)
    ]
    llm = AsyncMock()
    llm.generate_structured.return_value = RAGAnswer(
        answer="A USD 600 refund requires manager approval."
    )
    app.dependency_overrides[get_suggested_answer_service] = lambda: SuggestedAnswerService(
        tickets, RAGService(retrieval, llm)
    )

    response = client.post(f"/api/v1/tickets/{ticket_id}/suggested-answer")

    assert response.status_code == 200
    assert response.json() == {
        "ticket_id": str(ticket_id),
        "status": "draft",
        "suggested_answer": "A USD 600 refund requires manager approval.",
    }
    retrieval.retrieve.assert_awaited_once_with(
        "Can I get a refund?\n\nMy order was USD 600.", top_k=3, document_type=None
    )
    prompt = llm.generate_structured.await_args.kwargs["prompt"]
    assert "Refunds above USD 500 require manager approval." in prompt
    assert prompt.endswith("QUESTION\nCan I get a refund?\n\nMy order was USD 600.")


def test_suggested_answer_without_relevant_chunks_returns_existing_fallback(client) -> None:
    ticket_id = uuid4()
    tickets = AsyncMock()
    tickets.get.return_value = Ticket(id=ticket_id, title="Unknown policy", description="Help?")
    retrieval = AsyncMock()
    retrieval.retrieve.return_value = []
    llm = AsyncMock()
    app.dependency_overrides[get_suggested_answer_service] = lambda: SuggestedAnswerService(
        tickets, RAGService(retrieval, llm)
    )

    response = client.post(f"/api/v1/tickets/{ticket_id}/suggested-answer")

    assert response.status_code == 200
    assert response.json() == {
        "ticket_id": str(ticket_id),
        "status": "draft",
        "suggested_answer": RAGService.INSUFFICIENT_INFORMATION_ANSWER,
    }
    llm.generate_structured.assert_not_awaited()


def test_suggested_answer_for_unknown_ticket_returns_404(client) -> None:
    ticket_id = uuid4()
    tickets = AsyncMock()
    tickets.get.return_value = None
    rag = AsyncMock()
    app.dependency_overrides[get_suggested_answer_service] = lambda: SuggestedAnswerService(
        tickets, rag
    )

    response = client.post(f"/api/v1/tickets/{ticket_id}/suggested-answer")

    assert response.status_code == 404
    assert response.json() == {"detail": "Ticket not found"}
    rag.answer.assert_not_awaited()
