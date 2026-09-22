import asyncio
import os

import pytest
from app.llm.providers.gemini import GeminiLLMClient
from app.schemas.ticket_ai_analysis import TicketAIAnalysisOutput


@pytest.mark.integration
def test_gemini_analyzes_duplicate_card_charge() -> None:
    """Verify the real Gemini provider returns the requested ticket structure."""

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY is not configured")

    client = GeminiLLMClient(
        api_key=api_key,
        model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash"),
        timeout=float(os.getenv("GEMINI_TIMEOUT", "30")),
    )

    result = asyncio.run(
        client.generate_structured(
            prompt=(
                "My card was charged twice for the same order. "
                "Please refund the duplicate charge."
            ),
            response_model=TicketAIAnalysisOutput,
        )
    )
    print(result.model_dump_json(indent=2))

    assert result.category.value == "billing"
    assert result.priority.value in {"low", "medium", "high", "urgent"}
    assert result.summary.strip()
    assert isinstance(result.requires_human, bool)
