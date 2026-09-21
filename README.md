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

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy app
```

Project rules live in `.github/copilot-instructions.md`; component rules live in
`.github/instructions/`.
