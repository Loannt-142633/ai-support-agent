"""HTTP contract for the guarded local staff-agent demo."""

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from app.api.demo_staff import (
    DemoStaffAuth,
    DemoTicketAccess,
    get_demo_staff_auth,
    get_demo_ticket_access,
)
from app.api.dependencies import (
    get_gemini_staff_agent_model,
    get_ticket_analysis_publisher,
    get_ticket_repository,
)
from app.core.config import Settings
from app.llm.exceptions import LLMProviderError, LLMTimeoutError
from app.main import app, create_app
from app.services.agent_service import AgentToolCall, AgentTurn
from fastapi.testclient import TestClient


def _enable_demo(ticket_ids: list[UUID]) -> Settings:
    settings = Settings(
        app_env="local",
        demo_staff_auth_enabled=True,
        demo_staff_ticket_ids=ticket_ids,
        debug=False,
        _env_file=None,
    )
    app.dependency_overrides[get_demo_staff_auth] = lambda: DemoStaffAuth(settings)
    app.dependency_overrides[get_demo_ticket_access] = lambda: DemoTicketAccess(settings)
    return settings


def _create_ticket(client: TestClient) -> UUID:
    app.dependency_overrides[get_ticket_analysis_publisher] = lambda: AsyncMock()
    user = client.post(
        "/api/v1/users", json={"name": "Demo customer", "email": "agent-demo@example.com"}
    )
    assert user.status_code == 201
    ticket = client.post(
        "/api/v1/tickets",
        json={
            "user_id": user.json()["id"],
            "title": "Payment question",
            "description": "Please check my order.",
        },
    )
    assert ticket.status_code == 201
    return UUID(ticket.json()["id"])


def _demo_app(settings: Settings):
    demo_app = create_app(settings)
    demo_app.dependency_overrides.update(app.dependency_overrides)
    return demo_app


def _local_client(settings: Settings) -> TestClient:
    return TestClient(_demo_app(settings), client=("127.0.0.1", 50000))


def test_demo_endpoint_is_disabled_by_default(client: TestClient) -> None:
    ticket_id = uuid4()
    app.dependency_overrides[get_gemini_staff_agent_model] = lambda: pytest.fail(
        "Gemini model must not be created"
    )
    response = client.post(
        f"/api/v1/tickets/{ticket_id}/agent/ask", json={"message": "Paid?"}
    )
    assert response.status_code == 404
    assert "/api/v1/tickets/{ticket_id}/agent/ask" not in app.openapi()["paths"]


def test_non_allowlisted_ticket_never_loads_ticket_or_model(client: TestClient) -> None:
    settings = _enable_demo([uuid4()])
    tickets = AsyncMock()
    tickets.get.side_effect = AssertionError("Ticket should not be loaded")
    app.dependency_overrides[get_ticket_repository] = lambda: tickets
    app.dependency_overrides[get_gemini_staff_agent_model] = lambda: pytest.fail(
        "Gemini model must not be created"
    )
    response = _local_client(settings).post(
        f"/api/v1/tickets/{uuid4()}/agent/ask", json={"message": "Paid?"}
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "Ticket is not allowed for demo staff"}
    tickets.get.assert_not_awaited()


def test_allowlisted_missing_ticket_returns_404_without_model(client: TestClient) -> None:
    ticket_id = uuid4()
    settings = _enable_demo([ticket_id])
    app.dependency_overrides[get_gemini_staff_agent_model] = lambda: pytest.fail(
        "Gemini model must not be created"
    )
    response = _local_client(settings).post(
        f"/api/v1/tickets/{ticket_id}/agent/ask", json={"message": "Paid?"}
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Ticket not found"}


@pytest.mark.parametrize("message", ["", "  ", "\n\t"])
def test_blank_message_returns_422(client: TestClient, message: str) -> None:
    ticket_id = _create_ticket(client)
    settings = _enable_demo([ticket_id])
    model = AsyncMock()
    app.dependency_overrides[get_gemini_staff_agent_model] = lambda: model
    response = _local_client(settings).post(
        f"/api/v1/tickets/{ticket_id}/agent/ask", json={"message": message}
    )
    assert response.status_code == 422
    model.start.assert_not_awaited()


def test_allowed_ticket_returns_fake_agent_answer(client: TestClient) -> None:
    ticket_id = _create_ticket(client)
    settings = _enable_demo([ticket_id])
    model = AsyncMock()
    model.start.return_value = AgentTurn("  This is a demo answer.  ")
    app.dependency_overrides[get_gemini_staff_agent_model] = lambda: model
    assert "/api/v1/tickets/{ticket_id}/agent/ask" in _demo_app(settings).openapi()["paths"]

    response = _local_client(settings).post(
        f"/api/v1/tickets/{ticket_id}/agent/ask",
        json={"message": "  Check my order  "},
        headers={"X-Staff-Id": "admin", "X-Is-Admin": "true"},
    )
    assert response.status_code == 200
    assert response.json() == {"ticket_id": str(ticket_id), "answer": "This is a demo answer."}
    model.start.assert_awaited_once_with("Check my order")
    model.finish.assert_not_awaited()


def test_client_claimed_staff_fields_cannot_be_used_as_auth(client: TestClient) -> None:
    ticket_id = _create_ticket(client)
    settings = _enable_demo([ticket_id])
    model = AsyncMock()
    app.dependency_overrides[get_gemini_staff_agent_model] = lambda: model
    response = _local_client(settings).post(
        f"/api/v1/tickets/{ticket_id}/agent/ask",
        json={"message": "Paid?", "staff_id": "admin", "is_admin": True},
    )
    assert response.status_code == 422
    model.start.assert_not_awaited()


def test_agent_payment_tool_uses_ticket_customer_not_client_claim(client: TestClient) -> None:
    ticket_id = _create_ticket(client)
    settings = _enable_demo([ticket_id])
    model = AsyncMock()
    model.start.return_value = AgentTurn(
        None, (AgentToolCall("get_order_payments", {"order_id": "ORD-DEMO-SINGLE"}),)
    )
    model.finish.return_value = AgentTurn("This order is unavailable for this ticket.")
    app.dependency_overrides[get_gemini_staff_agent_model] = lambda: model
    response = _local_client(settings).post(
        f"/api/v1/tickets/{ticket_id}/agent/ask",
        json={"message": "Check ORD-DEMO-SINGLE"},
        headers={"X-User-Id": "00000000-0000-4000-8000-000000000001"},
    )
    assert response.status_code == 200
    assert model.finish.await_args.args[1]["error"]["code"] == "access_denied"


@pytest.mark.parametrize(
    ("failure", "status_code", "detail"),
    [
        (LLMTimeoutError("API key secret"), 504, "Agent timed out"),
        (LLMProviderError("API key secret"), 502, "Agent is unavailable"),
    ],
)
def test_llm_failure_is_safe(
    client: TestClient, failure: Exception, status_code: int, detail: str
) -> None:
    ticket_id = _create_ticket(client)
    settings = _enable_demo([ticket_id])
    model = AsyncMock()
    model.start.side_effect = failure
    app.dependency_overrides[get_gemini_staff_agent_model] = lambda: model
    response = _local_client(settings).post(
        f"/api/v1/tickets/{ticket_id}/agent/ask", json={"message": "Paid?"}
    )
    assert response.status_code == status_code
    assert response.json() == {"detail": detail}
    assert "secret" not in response.text


def test_remote_peer_cannot_use_demo_even_with_client_claims(client: TestClient) -> None:
    ticket_id = uuid4()
    settings = _enable_demo([ticket_id])
    response = TestClient(_demo_app(settings), client=("198.51.100.12", 50000)).post(
        f"/api/v1/tickets/{ticket_id}/agent/ask",
        json={"message": "Paid?", "staff_id": "local-demo-staff"},
        headers={"X-Forwarded-For": "127.0.0.1", "X-Staff-Role": "admin"},
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "Demo agent requires loopback access"}
