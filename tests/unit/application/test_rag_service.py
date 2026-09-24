import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.repositories.document_chunk_repository import SimilarDocumentChunk
from app.schemas.rag import RAGAnswer
from app.services.rag_service import RAGService


def test_answer_retrieves_context_and_calls_llm_with_grounded_prompt() -> None:
    retrieval = AsyncMock()
    llm_client = AsyncMock()
    retrieval.retrieve.return_value = [
        SimilarDocumentChunk(uuid4(), 1, "Refunds above USD 500 require manager approval.", 0.1),
        SimilarDocumentChunk(uuid4(), 2, "Eligible refunds require payment verification.", 0.2),
    ]
    llm_client.generate_structured.return_value = RAGAnswer(
        answer="A $600 refund requires manager approval."
    )

    result = asyncio.run(
        RAGService(retrieval, llm_client).answer(
            "  Can I get a refund for a $600 order?  ",
            top_k=3,
            document_type="refund_policy",
        )
    )

    assert result == "A $600 refund requires manager approval."
    retrieval.retrieve.assert_awaited_once_with(
        "Can I get a refund for a $600 order?",
        top_k=3,
        document_type="refund_policy",
    )
    request = llm_client.generate_structured.await_args.kwargs
    assert request["response_model"] is RAGAnswer
    assert request["prompt"].startswith("INSTRUCTION\n\n- Answer only using")
    assert "[Chunk 1]\nRefunds above USD 500 require manager approval." in request["prompt"]
    assert "[Chunk 2]\nEligible refunds require payment verification." in request["prompt"]
    assert request["prompt"].endswith(
        "QUESTION\nCan I get a refund for a $600 order?"
    )


def test_answer_returns_insufficient_information_without_calling_llm() -> None:
    retrieval = AsyncMock()
    llm_client = AsyncMock()
    retrieval.retrieve.return_value = []

    result = asyncio.run(RAGService(retrieval, llm_client).answer("Unknown policy?"))

    assert result == RAGService.INSUFFICIENT_INFORMATION_ANSWER
    retrieval.retrieve.assert_awaited_once_with(
        "Unknown policy?", top_k=3, document_type=None
    )
    llm_client.generate_structured.assert_not_awaited()


@pytest.mark.parametrize("question", ["", " \n\t"])
def test_answer_rejects_blank_question_before_retrieval(question: str) -> None:
    retrieval = AsyncMock()
    llm_client = AsyncMock()

    with pytest.raises(ValueError, match="question"):
        asyncio.run(RAGService(retrieval, llm_client).answer(question))

    retrieval.retrieve.assert_not_awaited()
    llm_client.generate_structured.assert_not_awaited()
