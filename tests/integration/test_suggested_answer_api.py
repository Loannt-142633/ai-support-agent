"""HTTP flow for persisting and reopening an unsent support reply draft."""

from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from app.api.dependencies import get_retrieval_service, get_ticket_analysis_publisher
from app.main import app
from app.repositories.document_chunk_repository import SimilarDocumentChunk
from app.schemas.rag import RAGAnswer
from app.services.rag_service import RAGService


def _create_ticket(client) -> UUID:
    app.dependency_overrides[get_ticket_analysis_publisher] = lambda: AsyncMock()
    user = client.post(
        "/api/v1/users", json={"name": "Ada Lovelace", "email": "ada@example.com"}
    )
    assert user.status_code == 201
    ticket = client.post(
        "/api/v1/tickets",
        json={
            "user_id": user.json()["id"],
            "title": "Can I get a refund?",
            "description": "My order was USD 600.",
        },
    )
    assert ticket.status_code == 201
    return UUID(ticket.json()["id"])


def test_suggested_answer_persists_sources_and_get_does_not_regenerate(client) -> None:
    ticket_id = _create_ticket(client)
    retrieval = AsyncMock()
    first = SimilarDocumentChunk(uuid4(), 4, "Manager approval above USD 500.", 0.1)
    second = SimilarDocumentChunk(uuid4(), 2, "Verify payment eligibility.", 0.2)
    retrieval.retrieve.return_value = [first, second]
    app.dependency_overrides[get_retrieval_service] = lambda: retrieval
    llm = AsyncMock()
    llm.generate_structured.return_value = RAGAnswer(
        answer="Eligibility must be verified; manager approval is required."
    )

    with patch("app.api.dependencies.get_llm_client", return_value=llm):
        created = client.post(f"/api/v1/tickets/{ticket_id}/suggested-answer")
        assert created.status_code == 200
        body = created.json()
        draft_id = UUID(body["draft_id"])
        assert body["ticket_id"] == str(ticket_id)
        assert body["status"] == "draft"
        assert body["staff_content"] is None
        assert body["updated_at"] is None
        assert body["reviewed_at"] is None
        assert body["rejection_reason"] is None
        assert body["suggested_answer"] == (
            "Eligibility must be verified; manager approval is required."
        )
        assert body["created_at"]
        assert body["sources"] == [
            {"document_id": str(first.document_id), "chunk_index": first.chunk_index},
            {"document_id": str(second.document_id), "chunk_index": second.chunk_index},
        ]
        prompt = llm.generate_structured.await_args.kwargs["prompt"]
        assert prompt.index(first.content) < prompt.index(second.content)

        reopened = client.get(f"/api/v1/tickets/{ticket_id}/suggested-answers/{draft_id}")

    assert reopened.status_code == 200
    assert reopened.json() == body
    retrieval.retrieve.assert_awaited_once_with(
        "Can I get a refund?\n\nMy order was USD 600.", top_k=3, document_type=None
    )
    llm.generate_structured.assert_awaited_once()

    wrong_ticket = client.get(f"/api/v1/tickets/{uuid4()}/suggested-answers/{draft_id}")
    assert wrong_ticket.status_code == 404
    missing_draft = client.get(f"/api/v1/tickets/{ticket_id}/suggested-answers/{uuid4()}")
    assert missing_draft.status_code == 404


def test_suggested_answer_without_relevant_chunks_persists_fallback(client) -> None:
    ticket_id = _create_ticket(client)
    retrieval = AsyncMock()
    retrieval.retrieve.return_value = []
    app.dependency_overrides[get_retrieval_service] = lambda: retrieval

    with patch("app.api.dependencies.get_llm_client", side_effect=AssertionError("LLM called")):
        response = client.post(f"/api/v1/tickets/{ticket_id}/suggested-answer")

    assert response.status_code == 200
    assert response.json()["suggested_answer"] == RAGService.INSUFFICIENT_INFORMATION_ANSWER
    assert response.json()["sources"] == []
    draft_id = response.json()["draft_id"]
    reopened = client.get(f"/api/v1/tickets/{ticket_id}/suggested-answers/{draft_id}")
    assert reopened.json() == response.json()


def test_suggested_answer_for_unknown_ticket_returns_404_without_llm(client) -> None:
    retrieval = AsyncMock()
    app.dependency_overrides[get_retrieval_service] = lambda: retrieval
    ticket_id = uuid4()

    with patch("app.api.dependencies.get_llm_client", side_effect=AssertionError("LLM called")):
        response = client.post(f"/api/v1/tickets/{ticket_id}/suggested-answer")

    assert response.status_code == 404
    assert response.json() == {"detail": "Ticket not found"}
    retrieval.retrieve.assert_not_awaited()


def test_staff_can_edit_then_approve_only_once(client) -> None:
    ticket_id = _create_ticket(client)
    retrieval = AsyncMock()
    retrieval.retrieve.return_value = []
    app.dependency_overrides[get_retrieval_service] = lambda: retrieval
    created = client.post(f"/api/v1/tickets/{ticket_id}/suggested-answer")
    assert created.status_code == 200
    draft_id = created.json()["draft_id"]
    url = f"/api/v1/tickets/{ticket_id}/suggested-answers/{draft_id}"

    edited = client.patch(url, json={"staff_content": "  Please verify your payment.  "})
    assert edited.status_code == 200
    assert edited.json()["status"] == "draft"
    assert edited.json()["staff_content"] == "Please verify your payment."
    assert edited.json()["suggested_answer"] == RAGService.INSUFFICIENT_INFORMATION_ANSWER
    assert edited.json()["updated_at"] is not None
    assert edited.json()["reviewed_at"] is None

    approved = client.post(f"{url}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["staff_content"] == "Please verify your payment."
    assert approved.json()["reviewed_at"] is not None
    assert approved.json()["rejection_reason"] is None

    assert client.post(f"{url}/approve").status_code == 409
    assert client.post(f"{url}/reject", json={"reason": "Too vague"}).status_code == 409
    assert client.patch(url, json={"staff_content": "Changed"}).status_code == 409
    assert client.get(url).json() == approved.json()


def test_rejected_draft_keeps_reason_and_cannot_be_approved(client) -> None:
    ticket_id = _create_ticket(client)
    retrieval = AsyncMock()
    retrieval.retrieve.return_value = []
    app.dependency_overrides[get_retrieval_service] = lambda: retrieval
    created = client.post(f"/api/v1/tickets/{ticket_id}/suggested-answer")
    draft_id = created.json()["draft_id"]
    url = f"/api/v1/tickets/{ticket_id}/suggested-answers/{draft_id}"

    assert client.post(f"{url}/reject", json={"reason": "   "}).status_code == 422
    rejected = client.post(f"{url}/reject", json={"reason": "  Missing policy evidence.  "})
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["rejection_reason"] == "Missing policy evidence."
    assert rejected.json()["reviewed_at"] is not None
    assert client.post(f"{url}/approve").status_code == 409
    assert client.post(f"{url}/reject", json={"reason": "Again"}).status_code == 409
    assert client.get(url).json() == rejected.json()
