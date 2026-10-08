"""Authorized ticket notification WebSockets and Redis fan-out."""

import asyncio
import json
import logging
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.demo_staff import DemoStaffAuth, DemoTicketAccess
from app.core.config import Settings
from app.db.session import get_db
from app.repositories.ticket_repository import TicketRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/tickets", tags=["notifications"])


class TicketConnectionManager:
    """Keep local WebSocket connections grouped by authorized ticket ID."""

    def __init__(self) -> None:
        self._connections: dict[UUID, set[WebSocket]] = defaultdict(set)

    async def connect(self, ticket_id: UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[ticket_id].add(websocket)

    def disconnect(self, ticket_id: UUID, websocket: WebSocket) -> None:
        sockets = self._connections.get(ticket_id)
        if sockets is not None:
            sockets.discard(websocket)
            if not sockets:
                self._connections.pop(ticket_id, None)

    async def broadcast(self, ticket_id: UUID, payload: dict[str, object]) -> None:
        for websocket in tuple(self._connections.get(ticket_id, ())):
            try:
                await asyncio.wait_for(websocket.send_json(payload), timeout=2)
            except (OSError, RuntimeError, TimeoutError):
                self.disconnect(ticket_id, websocket)


def decode_notification(data: bytes) -> tuple[UUID, dict[str, object]]:
    """Accept only the Redis contract emitted by the notification worker."""
    try:
        payload = json.loads(data)
        if (
            not isinstance(payload, dict)
            or payload.get("version") != 1
            or payload.get("event") != "analysis.completed"
            or not isinstance(payload.get("ticket_id"), str)
            or not isinstance(payload.get("analysis_id"), str)
        ):
            raise ValueError("Invalid notification")
        ticket_id = UUID(payload["ticket_id"])
        analysis_id = UUID(payload["analysis_id"])
        return ticket_id, {
            "version": 1,
            "event": "analysis.completed",
            "ticket_id": str(ticket_id),
            "analysis_id": str(analysis_id),
        }
    except (UnicodeDecodeError, TypeError, ValueError) as error:
        raise ValueError("Invalid notification") from error


async def listen_notifications(
    redis: Redis, channel: str, manager: TicketConnectionManager
) -> None:
    """Retry Redis subscription after an outage; malformed messages are skipped."""
    while True:
        try:
            async with redis.pubsub() as pubsub:
                await pubsub.subscribe(channel)
                logger.info("Subscribed to Redis channel %s", channel)
                while True:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
                    if message is None:
                        continue
                    try:
                        ticket_id, payload = decode_notification(message["data"])
                    except ValueError:
                        logger.warning("Skipped invalid Redis notification")
                        continue
                    await manager.broadcast(ticket_id, payload)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Redis notification listener disconnected; retrying")
            await asyncio.sleep(1)


@asynccontextmanager
async def notification_lifespan(
    settings: Settings, manager: TicketConnectionManager
) -> AsyncIterator[None]:
    redis = Redis.from_url(settings.redis_url)
    listener = asyncio.create_task(
        listen_notifications(redis, settings.redis_notification_channel, manager)
    )
    try:
        yield
    finally:
        listener.cancel()
        try:
            await listener
        except asyncio.CancelledError:
            pass
        await redis.aclose()


@router.websocket("/{ticket_id}/notifications/ws")
async def ticket_notifications(
    websocket: WebSocket,
    ticket_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Stream IDs only after the local demo identity and ticket allowlist pass."""
    settings: Settings = websocket.app.state.settings
    try:
        staff = DemoStaffAuth(settings).authenticate(websocket)
        DemoTicketAccess(settings).require(ticket_id, staff)
        origin = websocket.headers.get("origin")
        if origin is not None and origin not in settings.cors_origins:
            await websocket.close(code=1008)
            return
        if await TicketRepository(session).get(ticket_id) is None:
            await websocket.close(code=1008)
            return
    except HTTPException:
        await websocket.close(code=1008)
        return

    manager: TicketConnectionManager = websocket.app.state.notification_manager
    await manager.connect(ticket_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ticket_id, websocket)
