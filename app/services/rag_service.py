"""Retrieval-augmented question answering workflow."""

from app.llm.client import LLMClient
from app.repositories.document_chunk_repository import SimilarDocumentChunk
from app.schemas.rag import RAGAnswer
from app.services.retrieval_service import RetrievalService


class RAGService:
    """Retrieve relevant policy context and generate a grounded answer."""

    INSUFFICIENT_INFORMATION_ANSWER = (
        "The available information is insufficient to answer this question."
    )

    def __init__(self, retrieval: RetrievalService, llm_client: LLMClient) -> None:
        self._retrieval = retrieval
        self._llm_client = llm_client

    async def answer(
        self,
        question: str,
        *,
        top_k: int = 3,
        document_type: str | None = None,
    ) -> str:
        """Answer a question using only retrieved document chunks."""

        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question must not be empty")

        chunks = await self._retrieval.retrieve(
            normalized_question,
            top_k=top_k,
            document_type=document_type,
        )
        if not chunks:
            return self.INSUFFICIENT_INFORMATION_ANSWER

        response = await self._llm_client.generate_structured(
            prompt=self._build_prompt(normalized_question, chunks),
            response_model=RAGAnswer,
        )
        return response.answer

    @staticmethod
    def _build_prompt(
        question: str,
        chunks: list[SimilarDocumentChunk],
    ) -> str:
        """Build a grounded prompt with numbered chunks in retrieval order."""

        context = "\n\n".join(
            f"[Chunk {index}]\n{chunk.content}"
            for index, chunk in enumerate(chunks, start=1)
        )
        return f"""INSTRUCTION

- Answer only using the provided context.
- Do not invent policies or rules.
- If the context does not contain enough information,
  say that the available information is insufficient.
- Do not claim that an action was executed.
- Clearly distinguish a policy requirement from a recommendation.

CONTEXT
{context}

QUESTION
{question}"""
