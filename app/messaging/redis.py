"""Redis Pub/Sub transport for ticket notifications."""

import json

from redis.asyncio import Redis

from app.services.analysis_completed_publisher import AnalysisCompleted


class RedisAnalysisNotificationPublisher:
    """Publish analysis identity for real-time staff notification subscribers."""

    def __init__(self, redis: Redis, *, channel: str) -> None:
        if not channel.strip():
            raise ValueError("Redis notification channel must be configured")
        self._redis = redis
        self._channel = channel

    async def publish(self, event: AnalysisCompleted) -> None:
        payload = json.dumps(
            {
                "version": 1,
                "event": "analysis.completed",
                "ticket_id": str(event.ticket_id),
                "analysis_id": str(event.analysis_id),
            },
            separators=(",", ":"),
        )
        await self._redis.publish(self._channel, payload)
