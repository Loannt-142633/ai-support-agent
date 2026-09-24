import asyncio

import pytest
from app.core.config import get_settings
from app.llm.providers.gemini import GeminiLLMClient
from app.schemas.ticket_ai_analysis import TicketAIAnalysisOutput


@pytest.mark.integration
def test_gemini_analyzes_duplicate_card_charge() -> None:
    """Verify the real Gemini provider returns the requested ticket structure."""

    settings = get_settings()
    if not settings.gemini_api_key.strip():
        pytest.skip("GEMINI_API_KEY is not configured")

    client = GeminiLLMClient(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        timeout=settings.gemini_timeout,
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
