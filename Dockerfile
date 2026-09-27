# syntax=docker/dockerfile:1

FROM python:3.12-slim AS dependencies

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY scripts/install_dependencies.py ./scripts/install_dependencies.py

RUN --mount=type=cache,target=/root/.cache/pip \
    python scripts/install_dependencies.py base

FROM dependencies AS embedding-dependencies

RUN --mount=type=cache,target=/root/.cache/pip \
    python scripts/install_dependencies.py embeddings

FROM dependencies AS base

COPY README.md alembic.ini ./
COPY app ./app
COPY migrations ./migrations

RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --no-build-isolation --no-deps . && \
    python -m pip check

FROM embedding-dependencies AS embedding-app

COPY README.md alembic.ini ./
COPY app ./app
COPY migrations ./migrations

RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --no-build-isolation --no-deps . && \
    python -m pip check

FROM embedding-app AS worker

CMD ["ai-support-worker"]

FROM embedding-app AS api

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
