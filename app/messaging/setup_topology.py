"""Provision the document ingestion dead-letter route through RabbitMQ's HTTP API."""

import base64
import json
import logging
import re
from urllib.parse import quote, unquote, urlsplit
from urllib.request import Request, urlopen

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def configure_document_ingestion_topology(
    *, rabbitmq_url: str, management_url: str, queue_name: str
) -> None:
    """Declare both queues, the DLX/binding, and an updateable DLX policy."""

    connection = urlsplit(rabbitmq_url)
    if connection.username is None or connection.password is None:
        raise ValueError("RabbitMQ URL must include management credentials")
    if not queue_name.strip():
        raise ValueError("Document ingestion queue name must not be empty")

    vhost = quote(unquote(connection.path.lstrip("/")) or "/", safe="")
    authorization = base64.b64encode(
        f"{unquote(connection.username)}:{unquote(connection.password)}".encode()
    ).decode("ascii")
    base_url = management_url.rstrip("/")
    exchange_name = f"{queue_name}.dlx"
    failed_queue_name = f"{queue_name}.failed"
    exchange = quote(exchange_name, safe="")
    failed_queue = quote(failed_queue_name, safe="")
    source_queue = quote(queue_name, safe="")

    def send(method: str, path: str, payload: dict[str, object]) -> None:
        request = Request(
            f"{base_url}/api/{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Basic {authorization}",
                "Content-Type": "application/json",
            },
            method=method,
        )
        with urlopen(request, timeout=10):
            pass

    durable_queue = {"durable": True, "auto_delete": False, "arguments": {}}
    send(
        "PUT",
        f"exchanges/{vhost}/{exchange}",
        {
            "type": "direct",
            "durable": True,
            "auto_delete": False,
            "internal": False,
            "arguments": {},
        },
    )
    send("PUT", f"queues/{vhost}/{failed_queue}", durable_queue)
    send(
        "POST",
        f"bindings/{vhost}/e/{exchange}/q/{failed_queue}",
        {"routing_key": failed_queue_name, "arguments": {}},
    )
    send("PUT", f"queues/{vhost}/{source_queue}", durable_queue)
    send(
        "PUT",
        f"policies/{vhost}/{quote(f'{queue_name}-dlx', safe='')}",
        {
            "pattern": f"^{re.escape(queue_name)}$",
            "definition": {
                "dead-letter-exchange": exchange_name,
                "dead-letter-routing-key": failed_queue_name,
            },
            "priority": 10,
            "apply-to": "queues",
        },
    )
    logger.info("Configured dead-letter route for %s to %s", queue_name, failed_queue_name)


def main() -> None:
    """Configure the broker before API publishers and workers start."""

    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    configure_document_ingestion_topology(
        rabbitmq_url=settings.rabbitmq_url,
        management_url=settings.rabbitmq_management_url,
        queue_name=settings.document_ingestion_queue,
    )


if __name__ == "__main__":
    main()
