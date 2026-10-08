"""Authorized ticket WebSocket delivery and Redis notification contract."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest
from app.api.notifications import (
    TicketConnectionManager,
    decode_notification,
    listen_notifications,
)
from app.core.config import Settings
from app.db.session import get_db
from app.main import create_app
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


@asynccontextmanager
async def _no_listener(
    _settings: Settings, _manager: TicketConnectionManager
) -> AsyncIterator[None]:
    yield


def _client(allowed_ticket_id: str | None) -> tuple[TestClient, TicketConnectionManager]:
    ticket_id = uuid4() if allowed_ticket_id is None else allowed_ticket_id
    settings = Settings(
        app_env="local",
        demo_staff_auth_enabled=True,
        demo_staff_ticket_ids=[ticket_id],
        debug=False,
        _env_file=None,
    )
    with patch("app.main.notification_lifespan", _no_listener):
        app = create_app(settings)

    async def fake_session() -> AsyncIterator[Mock]:
        yield Mock()

    app.dependency_overrides[get_db] = fake_session
    return TestClient(app, client=("127.0.0.1", 50000)), app.state.notification_manager


def test_websocket_receives_only_its_ticket_notification() -> None:
    ticket_id = uuid4()
    other_id = uuid4()
    client, manager = _client(str(ticket_id))
    path = f"/api/v1/tickets/{ticket_id}/notifications/ws"
    notification = {
        "version": 1,
        "event": "analysis.completed",
        "ticket_id": str(ticket_id),
        "analysis_id": str(uuid4()),
    }
    with (
        patch("app.api.notifications.TicketRepository.get", new_callable=AsyncMock) as get_ticket,
        client,
    ):
        get_ticket.return_value = Mock()
        with client.websocket_connect(path, headers={"origin": "http://localhost:3000"}) as socket:
            assert client.portal is not None
            client.portal.call(manager.broadcast, other_id, notification)
            client.portal.call(manager.broadcast, ticket_id, notification)
            assert socket.receive_json() == notification
        get_ticket.assert_awaited_once_with(ticket_id)


@pytest.mark.parametrize("reason", ["not_allowed", "wrong_origin", "not_found"])
def test_websocket_denies_unauthorized_ticket(reason: str) -> None:
    ticket_id = uuid4()
    allowed_id = uuid4() if reason == "not_allowed" else ticket_id
    client, _manager = _client(str(allowed_id))
    path = f"/api/v1/tickets/{ticket_id}/notifications/ws"
    origin = "https://foreign.example" if reason == "wrong_origin" else "http://localhost:3000"
    with (
        patch("app.api.notifications.TicketRepository.get", new_callable=AsyncMock) as get_ticket,
        client,
    ):
        get_ticket.return_value = None if reason == "not_found" else Mock()
        with pytest.raises(WebSocketDisconnect) as error:
            with client.websocket_connect(path, headers={"origin": origin}):
                pass
        assert error.value.code == 1008
        if reason == "not_allowed" or reason == "wrong_origin":
            get_ticket.assert_not_awaited()


def test_websocket_disabled_in_production() -> None:
    with patch("app.main.notification_lifespan", _no_listener):
        app = create_app(Settings(debug=False, _env_file=None))
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        with pytest.raises(WebSocketDisconnect) as error:
            with client.websocket_connect(f"/api/v1/tickets/{uuid4()}/notifications/ws"):
                pass
    assert error.value.code == 1008


def test_redis_notification_payload_validation() -> None:
    ticket_id = uuid4()
    analysis_id = uuid4()
    payload = {
        "version": 1,
        "event": "analysis.completed",
        "ticket_id": str(ticket_id),
        "analysis_id": str(analysis_id),
    }
    assert decode_notification(json.dumps(payload).encode()) == (ticket_id, payload)
    payload["analysis_id"] = "invalid"
    with pytest.raises(ValueError, match="Invalid notification"):
        decode_notification(json.dumps(payload).encode())


def test_redis_listener_forwards_valid_message_to_ticket_manager() -> None:
    ticket_id = uuid4()
    payload = {
        "version": 1,
        "event": "analysis.completed",
        "ticket_id": str(ticket_id),
        "analysis_id": str(uuid4()),
    }
    pubsub = Mock(subscribe=AsyncMock())
    first_message = {"data": json.dumps(payload).encode()}

    async def get_message(**_kwargs: object) -> dict[str, bytes] | None:
        if not delivered.is_set():
            return first_message
        await asyncio.sleep(10)
        return None

    pubsub.get_message = AsyncMock(side_effect=get_message)
    redis = Mock()
    redis.pubsub.return_value = MagicMock()
    redis.pubsub.return_value.__aenter__ = AsyncMock(return_value=pubsub)
    redis.pubsub.return_value.__aexit__ = AsyncMock(return_value=None)
    manager = TicketConnectionManager()
    delivered = asyncio.Event()

    async def broadcast(_ticket_id: object, _payload: object) -> None:
        delivered.set()

    manager.broadcast = AsyncMock(side_effect=broadcast)  # type: ignore[method-assign]

    async def run() -> None:
        task = asyncio.create_task(listen_notifications(redis, "ticket.notifications", manager))
        await asyncio.wait_for(delivered.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    pubsub.subscribe.assert_awaited_once_with("ticket.notifications")
    manager.broadcast.assert_awaited_once_with(ticket_id, payload)
