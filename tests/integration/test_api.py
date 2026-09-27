from unittest.mock import AsyncMock
from uuid import UUID

from app.api.dependencies import get_ticket_analysis_publisher
from app.main import app


def test_health_check(client) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_ticket(client) -> None:
    publisher = AsyncMock()
    app.dependency_overrides[get_ticket_analysis_publisher] = lambda: publisher
    user_response = client.post(
        "/api/v1/users",
        json={"name": "Ada Lovelace", "email": "ada@example.com"},
    )
    user_id = user_response.json()["id"]

    response = client.post(
        "/api/v1/tickets",
        json={
            "user_id": user_id,
            "title": "Cannot sign in",
            "description": "The reset link has expired.",
            "category": "general",
            "priority": "medium",
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "open"
    publisher.publish.assert_awaited_once_with(UUID(response.json()["id"]))
