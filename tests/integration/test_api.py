def test_health_check(client) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_ticket(client) -> None:
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
