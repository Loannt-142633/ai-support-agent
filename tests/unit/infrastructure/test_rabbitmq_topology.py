import base64
import json
from unittest.mock import MagicMock, patch
from urllib.error import URLError
from urllib.request import Request

import pytest
from app.messaging.setup_topology import configure_document_ingestion_topology


def test_configures_complete_dead_letter_route_with_queue_policy() -> None:
    requests: list[Request] = []

    def send(request: Request, *, timeout: int) -> MagicMock:
        assert timeout == 10
        requests.append(request)
        return MagicMock()

    with patch("app.messaging.setup_topology.urlopen", side_effect=send):
        configure_document_ingestion_topology(
            rabbitmq_url="amqp://app:app@rabbitmq:5672/",
            management_url="http://rabbitmq:15672",
            queue_name="document.ingestion",
        )

    assert [request.get_method() for request in requests] == [
        "PUT",
        "PUT",
        "POST",
        "PUT",
        "PUT",
    ]
    assert [request.full_url for request in requests] == [
        "http://rabbitmq:15672/api/exchanges/%2F/document.ingestion.dlx",
        "http://rabbitmq:15672/api/queues/%2F/document.ingestion.failed",
        "http://rabbitmq:15672/api/bindings/%2F/e/document.ingestion.dlx/q/document.ingestion.failed",
        "http://rabbitmq:15672/api/queues/%2F/document.ingestion",
        "http://rabbitmq:15672/api/policies/%2F/document.ingestion-dlx",
    ]
    bodies = [json.loads(request.data or b"") for request in requests]
    assert bodies[0] == {
        "type": "direct",
        "durable": True,
        "auto_delete": False,
        "internal": False,
        "arguments": {},
    }
    assert bodies[1] == bodies[3] == {
        "durable": True,
        "auto_delete": False,
        "arguments": {},
    }
    assert bodies[2] == {"routing_key": "document.ingestion.failed", "arguments": {}}
    assert bodies[4] == {
        "pattern": "^document\\.ingestion$",
        "definition": {
            "dead-letter-exchange": "document.ingestion.dlx",
            "dead-letter-routing-key": "document.ingestion.failed",
        },
        "priority": 10,
        "apply-to": "queues",
    }
    assert all(
        request.get_header("Authorization")
        == f"Basic {base64.b64encode(b'app:app').decode('ascii')}"
        for request in requests
    )


def test_setup_stops_before_policy_when_binding_fails() -> None:
    requests: list[Request] = []

    def send(request: Request, *, timeout: int) -> MagicMock:
        requests.append(request)
        if len(requests) == 3:
            raise URLError("binding failed")
        return MagicMock()

    with (
        patch("app.messaging.setup_topology.urlopen", side_effect=send),
        pytest.raises(URLError, match="binding failed"),
    ):
        configure_document_ingestion_topology(
            rabbitmq_url="amqp://app:app@rabbitmq:5672/",
            management_url="http://rabbitmq:15672",
            queue_name="document.ingestion",
        )

    assert len(requests) == 3
    assert requests[-1].get_method() == "POST"
