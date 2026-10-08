"""Redis Pub/Sub notification payload contract."""

import asyncio
import json
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from app.messaging.redis import RedisAnalysisNotificationPublisher
from app.services.analysis_completed_publisher import AnalysisCompleted


def test_publishes_analysis_identity_to_notification_channel() -> None:
    event = AnalysisCompleted(ticket_id=uuid4(), analysis_id=uuid4())
    redis = Mock(publish=AsyncMock(return_value=0))
    publisher = RedisAnalysisNotificationPublisher(redis, channel="ticket.notifications")
    asyncio.run(publisher.publish(event))
    redis.publish.assert_awaited_once()
    channel, raw_payload = redis.publish.await_args.args
    assert channel == "ticket.notifications"
    assert json.loads(raw_payload) == {
        "version": 1,
        "event": "analysis.completed",
        "ticket_id": str(event.ticket_id),
        "analysis_id": str(event.analysis_id),
    }
