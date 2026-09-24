"""Structured output schema for grounded answers."""

from pydantic import BaseModel, field_validator


class RAGAnswer(BaseModel):
    """A grounded natural-language answer returned by the LLM."""

    answer: str

    @field_validator("answer")
    @classmethod
    def answer_must_not_be_blank(cls, value: str) -> str:
        """Normalize and reject empty model answers."""

        normalized = value.strip()
        if not normalized:
            raise ValueError("answer must not be empty")
        return normalized
