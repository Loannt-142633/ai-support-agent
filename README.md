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

Create `.env` from `.env.example`, then start the API, worker, PostgreSQL, and RabbitMQ:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up --build -d
```

FastAPI is available at http://localhost:8000/docs. Compose runs Alembic
migrations before starting the API and the independent ingestion worker.
Both containers connect to PostgreSQL at `db:5432` and RabbitMQ at
`rabbitmq:5672`, and share uploaded files through the `uploads_data` Docker
volume. Set `GEMINI_API_KEY` in `.env` when using Gemini.

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

Compose starts RabbitMQ with the API; use `docker compose up -d rabbitmq` to
start only the broker for local Python development. The upload service
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

The worker ACKs successful jobs and rejects malformed or missing-document jobs
without requeue. Other handler failures are currently logged and left unacked;
their retry/rejection policy has not been implemented yet.

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

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy app
```

Project rules live in `.github/copilot-instructions.md`; component rules live in
`.github/instructions/`.
