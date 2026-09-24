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

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## PostgreSQL

The application uses PostgreSQL asynchronously through SQLAlchemy and the
`psycopg` async driver.
Start the local database with Docker:

```powershell
docker compose up -d db
```

The default connection string is:
`postgresql+psycopg://app:app@localhost:5432/ai_support_agent`.
Override `DATABASE_URL` in `.env` for another PostgreSQL instance.

Apply migrations:

```powershell
alembic upgrade head
```

The database layer uses `AsyncSession`; transaction commit and rollback are
owned by application services, while routes only handle HTTP mapping.

## Run

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

Semantic document chunking compares adjacent sentence embeddings and starts a new
chunk when cosine similarity falls below `CHUNK_SIMILARITY_THRESHOLD` (default
`0.85`). `MAX_CHUNK_SIZE` remains a strict character limit, including separators:
whole sentences are kept when possible; an oversized sentence is split at
whitespace, with character splitting for oversized words. Paragraph boundaries
are preserved when paragraphs share a chunk. Empty input returns `[]`.

Install the local embedding dependency before using semantic chunking:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[semantic]"
```

The model in `EMBEDDING_MODEL` is loaded lazily and reused. First use downloads
the model if it is not cached. Loading and inference run in a worker thread.
`CHUNK_EMBEDDING_PREFIX="query: "` follows the multilingual E5 model's
[semantic similarity guidance](https://huggingface.co/intfloat/multilingual-e5-base).
Adjust the prefix when changing models and calibrate the similarity threshold
with representative documents. Sentence detection currently uses punctuation
and blank lines; abbreviations can create extra sentence boundaries.

```python
from app.embeddings.sentence_transformer import SentenceTransformerEmbeddingClient
from app.services.chunking_service import ChunkingService

client = SentenceTransformerEmbeddingClient(
    "intfloat/multilingual-e5-base", prefix="query: "
)
chunker = ChunkingService(500, client, similarity_threshold=0.85)
chunks = await chunker.chunk(text)
```

`chunk()` is now async. Embedding errors propagate as `EmbeddingError`; the size
fallback does not hide provider failures. Unit tests use fake vectors without
downloading a model. The character limit is not an embedding-model token limit;
sentence-transformers applies its model's token truncation to long inputs.

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy app
```

Project rules live in `.github/copilot-instructions.md`; component rules live in
`.github/instructions/`.
