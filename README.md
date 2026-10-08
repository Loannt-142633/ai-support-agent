# AI Support Agent

FastAPI skeleton with an OOP/SOLID-oriented structure.

## Project structure

```text
ai-support-agent/
├── app/
│   ├── main.py          # FastAPI composition root
│   ├── api/             # Routes and dependency providers
│   ├── services/        # Business workflows and repository contracts
│   ├── llm/             # Provider-agnostic LLM boundaries
│   ├── schemas/         # HTTP request/response schemas
│   └── core/            # Configuration and cross-cutting settings
├── tests/
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

## Setup

Create `.env` from `.env.example`, then start the API, workers, PostgreSQL, and RabbitMQ:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up --build -d
```

FastAPI is available at http://localhost:8000/docs. Compose runs Alembic
migrations before starting the API and the independent ingestion worker.
Both containers connect to PostgreSQL at `db:5432` and RabbitMQ at
`rabbitmq:5672`, and share uploaded files through the `uploads_data` Docker
volume. Set `GEMINI_API_KEY` in `.env` when using Gemini.

Docker installs dependencies from `pyproject.toml` before copying application
source, so a Python code change reuses the dependency layers. BuildKit keeps
downloaded pip packages in a cache mount. API and document worker include the
E5 embedding packages; migration setup, RabbitMQ setup, and ticket worker use
the smaller base image. The first build after changing dependencies still needs
to download them; later builds reuse the cache.

For local Python development outside Docker, install dependencies with:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## PostgreSQL

The application uses PostgreSQL asynchronously through SQLAlchemy and the
`psycopg` async driver. Compose starts the database with the API. To start
only the database for local Python development:

```powershell
docker compose up -d db
```

Inside Compose, `DATABASE_URL` points to `db:5432`. When running Python on
the host, override it with
`postgresql+psycopg://app:app@localhost:5432/ai_support_agent`.

Compose applies migrations automatically. For local Python development, apply
them manually:

```powershell
alembic upgrade head
```

The database layer uses `AsyncSession`; transaction commit and rollback are
owned by application services, while routes only handle HTTP mapping.

## RabbitMQ document ingestion

Compose configures RabbitMQ before starting the API and worker; use
`docker compose up --build -d rabbitmq-setup` to start the broker and provision its
topology for local Python development. The upload service
publishes a persistent JSON message such as
`{"document_id":"<uuid>"}` to the durable `document.ingestion` queue after the
document metadata is committed. Inside Compose, `RABBITMQ_URL` points to
`rabbitmq:5672`. When running Python on the host, override it with
`amqp://app:app@localhost:5672/`. The separate worker consumes the queue and
closes its RabbitMQ connection when it receives SIGINT or SIGTERM. To start only
the worker and its infrastructure in Docker, run
`docker compose up --build -d worker`.

For local Python development, install the embedding extra and run the worker in
a second terminal:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[embeddings]"
$env:DATABASE_URL = "postgresql+psycopg://app:app@localhost:5432/ai_support_agent"
$env:RABBITMQ_URL = "amqp://app:app@localhost:5672/"
.\.venv\Scripts\python.exe -m app.worker
```

For host-based development, run the API against the same document storage path;
the worker opens the path saved with each uploaded document.

The worker tries a handler up to three times for recognized transient DB
connection/pool checkout failures or parser read connection failures/timeouts,
waiting three seconds between attempts.
The same delivery stays Unacked during each wait; the worker sends no NACK.
It ACKs once after success, or logs the failure and rejects without requeue
after the third attempt. Malformed messages, missing documents, corrupt PDFs,
and documents without extractable text are rejected immediately. Other handler
failures are also rejected without requeue. A `rabbitmq-setup` service declares
the durable `document.ingestion.dlx` direct exchange, the durable
`document.ingestion.failed` queue, and their binding. It applies a policy to
`document.ingestion` with `dead-letter-exchange=document.ingestion.dlx` and
`dead-letter-routing-key=document.ingestion.failed`. Rejected messages can be
inspected in the RabbitMQ management UI at http://localhost:15672. The failed
message carries RabbitMQ's `x-death` header;
the exception traceback remains in worker logs. The worker sets
`prefetch_count=1`, so each consumer receives at most one unacknowledged job at
a time. Before parsing, the handler checks for existing chunks; a sequentially
redelivered job is ACKed without parsing or embedding again. This does not
prevent two workers from processing the same document concurrently.

An uploaded document starts as `pending`. The worker commits `processing`
before parsing and embedding, then commits `completed` after the chunks are
stored. On a terminal failure it records `failed` with a short reason and
rejects the message to the failed queue. Query
`GET /api/v1/documents/{document_id}/status` to see `document_id`, `status`,
and `failure_reason` (`null` unless failed). Unknown IDs return 404. If a
worker stops after committing `processing`, a redelivered job may run again;
existing chunks are recognized as completed so they are not duplicated. If
the DB is unavailable when recording failure, the message is still rejected
to the failed queue and the status may remain `processing` until replayed.

## RabbitMQ ticket analysis

After a ticket is committed, the API publishes a persistent
`{"ticket_id":"<uuid>"}` message to the durable `ticket.analysis` queue.
The `rabbitmq-setup` service also provisions its dead-letter exchange,
`ticket.analysis.failed` queue, binding, and queue policy. Set
`TICKET_ANALYSIS_QUEUE` to override the source queue name. The independent
`ticket-worker` uses Gemini to classify, prioritize, summarize, and decide
whether human review is needed, then persists one `ticket_ai_analysis` record.
Set `GEMINI_API_KEY` before starting it. To run it on the host, use
`python -m app.ticket_worker`; Compose starts it with the other services.
It ACKs completed jobs (including sequential redeliveries), retries recognized
temporary DB, LLM timeout, and rate-limit failures up to three attempts, and
rejects terminal failures to `ticket.analysis.failed`. The existing-analysis
check prevents sequential duplicates; concurrent workers processing the same
ticket are not yet protected against duplicate records.
`GET /api/v1/tickets/{ticket_id}/analysis` returns `{"status":"pending"}`
while no analysis record exists, or `{"status":"completed", "category": ...,
"priority": ..., "summary": ..., "requires_human": ...}` once one is saved.
The response also includes `ticket_id`; an unknown ticket returns 404. Both
states use HTTP 200 because this is a read endpoint. `pending` means only
"no result in DB yet": the API cannot currently distinguish a running job
from a job lost between commit and publish or rejected to the failed queue.

Support staff can call `POST /api/v1/tickets/{ticket_id}/suggested-answer`
to generate a review-only draft from the ticket title and description. It
uses the existing RAG knowledge base and saves the answer in
`ticket_suggested_answers` with `draft_id`, `ticket_id`, `ai_content`,
`status: "draft"`, and `created_at`. The response also includes the chunk
references (`document_id` and `chunk_index`) supplied to the prompt, in order.
`GET /api/v1/tickets/{ticket_id}/suggested-answers/{draft_id}` opens the saved
draft without calling retrieval or the LLM. A draft belonging to another ticket
returns 404. No reply is sent to the customer. If retrieval finds no suitable
chunks, the insufficient-information answer is saved with no sources. An
unknown ticket returns 404.

Staff can save a revision with
`PATCH /api/v1/tickets/{ticket_id}/suggested-answers/{draft_id}` and body
`{"staff_content": "..."}`. This preserves the original `ai_content` and
leaves the status as `draft`. `POST .../{draft_id}/approve` approves the draft;
`POST .../{draft_id}/reject` requires `{"reason": "..."}`. Review time and,
for rejection, the reason are stored on the same draft. Both decisions are
terminal: later edits or another decision return HTTP 409. Approval does not
send a reply to the customer. There is no authenticated staff identity in the
current API, so reviewer identity is not recorded yet.

For email delivery, configure `SMTP_HOST`, `SMTP_FROM_EMAIL`, and optionally
`SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_STARTTLS`, and
`SMTP_TIMEOUT`. The adapter uses SMTP with STARTTLS by default (port 587).
`POST /api/v1/tickets/{ticket_id}/suggested-answers/{draft_id}/send` sends only
an `approved` draft to the ticket customer's email address. It prefers
`staff_content` over `ai_content`. The API commits `pending_send` before
contacting SMTP and records `sent` only when SMTP accepts the message; a
reported transport failure becomes `send_failed` and returns HTTP 502.
`sent` means SMTP accepted the message, not that it reached the recipient's
inbox. A send is not automatically retried: after a timeout or process crash,
`pending_send` may need manual reconciliation because SMTP does not guarantee
deduplication. Since staff authentication is intentionally deferred, the
edit/approve/reject/send endpoints must not be exposed publicly in production.

As with document uploads, a DB commit can succeed while publishing fails;
the ticket then remains saved without a queued analysis job. This gap needs
an outbox or equivalent reliability mechanism in a later step.

## Kafka ticket creation event

Compose starts a Kafka broker and creates the `ticket.created` topic with three
partitions. After a ticket is committed, the API publishes
`{"version":1,"ticket_id":"<uuid>"}` with the UTF-8 `ticket_id` as the Kafka
message key. Messages for the same ticket therefore map to the same partition.
The existing RabbitMQ ticket analysis job is still published separately.
Two independent workers subscribe to the same topic: `ticket-notifications`
and `ticket-metrics`. Each currently logs `ticket_id`, partition, offset, and
group ID, then commits that record's next offset. They do not send notifications
or calculate metrics yet. If parsing or logging fails, the offset is not
committed, so the worker exits and Compose restarts it for replay.

Inspect the workers with `docker compose logs -f ticket-notifications
ticket-metrics` after creating a ticket. Both groups receive every new event;
`auto_offset_reset=earliest` also lets a new group replay retained events.

Inside Compose, `KAFKA_BOOTSTRAP_SERVERS` is `kafka:9092`. For a host Python
process, set it to `localhost:9094`. The topic name can be set with
`TICKET_CREATED_TOPIC`. A failed Kafka publish raises an API error after the
ticket has already been saved. A transactional outbox is needed to close this
commit/publish gap in a later step.

## Run

The Docker command is `docker compose up --build -d`. For local Python
development outside Docker:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

## Postman

Import `postman/AI Support Agent.postman_collection.json` into Postman.
The collection uses `http://localhost:8000` by default and stores `user_id`
and `ticket_id` automatically after the create requests. Run the requests in
this order when starting with an empty database: Create user, Create ticket,
then the remaining user and ticket requests.

## Document chunking

Chunking normalizes line endings and horizontal whitespace, splits paragraphs
and sentences, and groups adjacent units within `MAX_CHUNK_SIZE` (default 500
characters). Separators count toward the limit. Oversized sentences are split
at whitespace; oversized words are split by character. Order and non-whitespace
content are preserved, and empty input returns `[]`.

`ChunkingService` is synchronous and requires no embedding model:

```python
from app.services.chunking_service import ChunkingService

chunks = ChunkingService(max_chunk_size=500).chunk(text)
```

Sentence detection uses punctuation and blank lines; abbreviations can create
extra boundaries. The size limit counts Python characters, not model tokens.

## Embedding support

`EmbeddingClient`, `EmbeddingInputType`, and `E5EmbeddingModel` support document
ingestion and future retrieval. Ingestion uses `DOCUMENT` (E5 `passage: `);
retrieval uses `QUERY` (E5 `query: `). Prefix mapping belongs to the E5 adapter.
`DocumentIngestionService` parses a stored document, chunks its text, embeds all
chunks as one batch, and persists the indexed chunk/vector pairs with one bulk
insert and one transaction commit. Retrieval is not implemented yet.

Install the optional dependency when using the embedding adapter:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[embeddings]"
```

The model configured in `EMBEDDING_MODEL` is loaded lazily and reused through
`get_embedding_client()`. First use downloads the model if it is not cached;
loading and inference run in a worker thread. Chunking does not load this model.

## Simulated order payments (internal demo)

`FakeOrderPaymentsRepository` provides deterministic in-memory data, **not results
from a payment provider**. No migration or dependency change is needed. An async `OrderPaymentsRepository` protocol allows
a future API/database adapter to replace the fake through constructor injection.

| Order ID | Payment attempts |
| --- | --- |
| `ORD-DEMO-SINGLE` | One succeeded payment of VND 125000.00 |
| `ORD-DEMO-DOUBLE` | Two succeeded payments of VND 125000.00 each |
| `ORD-DEMO-RETRY` | One failed and one succeeded attempt of VND 125000.00 each |
| `ORD-DEMO-EMPTY` | Existing order with no payments |
| `ORD-DEMO-MISSING` | Not found (as with any unknown ID) |

The internal Gemini declaration exposes only `order_id`. `StaffToolDispatcher`
accepts only `get_order_payments` and uses `ToolExecutionContext.ticket.user_id`,
never a customer ID supplied by the model. It returns JSON-compatible payment
facts (`Decimal` amounts as strings, UTC timestamps as ISO 8601), or a structured
error. It does not call Gemini or expose an HTTP endpoint.

For a demo with the default repository, first apply migrations and create a
customer with the fixed ID, then a ticket for that customer. For example, run
this once in a local Python session connected to the demo database:

```python
import asyncio
from app.db.session import SessionLocal
from app.models.ticket import Ticket
from app.models.user import User
from app.repositories.ticket_repository import TicketRepository
from app.repositories.fake_order_payments_repository import (
    DEMO_CUSTOMER_ID, FakeOrderPaymentsRepository,
)
from app.services.order_payments_service import OrderPaymentsService
from app.tools.order_payments import StaffToolDispatcher, load_tool_context

async def demo():
    async with SessionLocal() as session:
        customer = await session.get(User, DEMO_CUSTOMER_ID)
        if customer is None:
            session.add(User(
                id=DEMO_CUSTOMER_ID,
                name="Demo customer",
                email="payment-demo@example.invalid",
            ))
        ticket = Ticket(
            user_id=DEMO_CUSTOMER_ID,
            title="Payment question",
            description="Please check this order.",
        )
        session.add(ticket)
        await session.commit()
        context = await load_tool_context(ticket.id, TicketRepository(session))
        dispatcher = StaffToolDispatcher(OrderPaymentsService(FakeOrderPaymentsRepository()))
        result = await dispatcher.dispatch(
            "get_order_payments", {"order_id": "ORD-DEMO-DOUBLE"}, context
        )
        print(result)

asyncio.run(demo())
```

Successful tool results include `order_id`, `status` (`found` or `not_found`),
`payments`, and `source` with `is_simulated=True`. For example, the demo call
above returns `status: "found"`, two `succeeded` payments with
`amount: "125000.00"`, and `source.name: "fake_order_payments"`.
`ORD-DEMO-MISSING` returns `not_found` with `payments: []`;
`ORD-DEMO-EMPTY` returns `found` with `payments: []`.
Service records remain immutable with `Decimal` amounts and fixed UTC times.
Two successful payments are facts for investigating a
possible duplicate, not proof of one; the failed attempt in `ORD-DEMO-RETRY`
must not count as money collected. This service makes no duplicate-charge verdict.

The default synthetic customer UUID is `00000000-0000-4000-8000-000000000001`;
it is **not seeded into users**. For an existing local demo ticket, an explicit
backend setup can instead use `FakeOrderPaymentsRepository(demo_customer_id=ticket.user_id)`
with a non-null customer ID. Never construct this adapter from function-call
arguments or silently bind every ticket to the demo orders.
The service rejects missing or mismatched ticket customers with
`OrderPaymentsAccessError`. The caller must load the ticket from trusted storage;
never accept its customer ID from the LLM or treat it as staff authentication.
Real staff identity and ticket-access authorization remain unimplemented. The code
above is for a trusted local test; authenticate and authorize staff to the ticket
before calling `load_tool_context` in a future production workflow. Future adapters must supply a
verified order/customer mapping and truthful provenance.

## Internal staff agent (Gemini)

`AgentService` accepts a staff question and a backend-loaded `ToolExecutionContext`.
It asks Gemini with the `get_order_payments` declaration. If Gemini requests the
tool, the service runs `StaffToolDispatcher` once and sends its JSON-compatible
result back to Gemini for the final answer. A direct answer uses one model call;
a tool answer uses two. Further function calls are rejected. The Gemini SDK does
not execute functions automatically in this workflow.

After creating the demo ticket above and configuring `GEMINI_API_KEY`, the
internal call can be assembled as follows inside an async backend function:

```python
from app.core.config import get_settings
from app.llm.providers.gemini_staff_agent import GeminiStaffAgentModel
from app.services.agent_service import AgentService

settings = get_settings()
model = GeminiStaffAgentModel(
    api_key=settings.gemini_api_key,
    model=settings.gemini_model,
    timeout=settings.gemini_timeout,
)
agent = AgentService(model, StaffToolDispatcher(
    OrderPaymentsService(FakeOrderPaymentsRepository())
))
context = await load_tool_context(ticket_id, TicketRepository(session))
answer = await agent.answer("Check payments for ORD-DEMO-SINGLE", context=context)
```

Here `ticket_id` and `session` are backend values. The model controls only
the tool name and `order_id`, not the customer identity or access decision.

### Local demo API

The route `POST /api/v1/tickets/{ticket_id}/agent/ask` is registered **only**
when `APP_ENV=local` and `DEMO_STAFF_AUTH_ENABLED=true`. Both default to a
closed state. When demo auth is enabled with `APP_ENV=production`, the app
refuses to start. The Docker Compose API forces `APP_ENV=production`, so a
local demo flag accidentally left in `.env` cannot enable this route there.
Consequently, `docker compose up --build api` serves the normal API but returns
404 for `/agent/ask` by design. Rebuilding that service does not enable the
demo route.

Create the customer and ticket with `DEMO_CUSTOMER_ID` using the Python example
above. Copy the resulting ticket UUID into local `.env` and configure:

```dotenv
APP_ENV=local
DEMO_STAFF_AUTH_ENABLED=true
DEMO_STAFF_ID=local-demo-staff
DEMO_STAFF_TICKET_IDS=["paste-ticket-uuid-here"]
GEMINI_API_KEY=your-local-key
```

Replace the placeholder with a real UUID, or configuration validation will
reject startup. Multiple ticket IDs can be included in the JSON list. Restart
the local API after editing the allowlist, and bind it to loopback:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
$ticketId = "paste-ticket-uuid-here"
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/tickets/$ticketId/agent/ask" -ContentType "application/json" -Body '{"message":"Check payments for ORD-DEMO-SINGLE"}'
```

If the Compose API already occupies port 8000, leave its database and RabbitMQ
running and start a **separate host Python process** for the demo on port 8001.
The host process must use the published localhost database address (the Docker
hostname `db` works only inside Compose). In PowerShell:

```powershell
$ticketId = "paste-ticket-uuid-here"
$env:APP_ENV = "local"
$env:DEMO_STAFF_AUTH_ENABLED = "true"
$env:DEMO_STAFF_TICKET_IDS = '["' + $ticketId + '"]'
$env:DATABASE_URL = "postgresql+psycopg://app:app@localhost:5432/ai_support_agent"
$env:RABBITMQ_URL = "amqp://app:app@localhost:5672/"
$env:DEBUG = "false"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

In a second PowerShell terminal:

```powershell
$ticketId = "paste-ticket-uuid-here"
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8001/api/v1/tickets/$ticketId/agent/ask" -ContentType "application/json" -Body (@{ message = "Check payments for ORD-DEMO-SINGLE" } | ConvertTo-Json)
```

Set `GEMINI_API_KEY` in local `.env` before starting the host process. The
ticket must already exist in the same PostgreSQL database and be on the
allowlist; to inspect the fake order payments, its `user_id` must be
`DEMO_CUSTOMER_ID` as in the example above.

The response is `{"ticket_id":"...","answer":"..."}` for staff inspection;
it does not create a draft, approve one, or send email. The backend supplies a
fixed demo staff identity and permits only allowlisted tickets. The route also
rejects non-loopback peers without trusting forwarded headers or claimed staff
headers/body fields. An unknown allowed ticket returns 404, a non-allowlisted
ticket returns 403, and an empty message returns 422. Mock auth is only for
local testing: it cannot distinguish real staff members, and it must not be
exposed through a proxy. The fake payment adapter still maps orders only to
`DEMO_CUSTOMER_ID`, so other customers' tickets cannot read those orders.

Focused tests (after installing `.[dev]`):

```powershell
$env:DEBUG = "false"
.\.venv\Scripts\python.exe -m pytest tests/unit/application/test_order_payments_service.py tests/unit/application/test_order_payments_tool.py tests/unit/application/test_agent_service.py tests/unit/infrastructure/test_gemini_staff_agent.py
.\.venv\Scripts\python.exe -m pytest tests/integration/test_agent_api.py tests/unit/application/test_demo_staff_settings.py
```

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy app
```

Project rules live in `.github/copilot-instructions.md`; component rules live in
`.github/instructions/`.
