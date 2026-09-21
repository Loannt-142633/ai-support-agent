# AI Support Agent Project Rules

## Architecture
- Use a layered architecture: `domain` -> `application` -> `infrastructure` and `presentation`.
- Dependencies point inward. Domain code must not import FastAPI, Pydantic, SQLAlchemy, or infrastructure adapters.
- Use dependency inversion at boundaries with Protocols or abstract interfaces.
- Keep framework wiring in `presentation` and composition roots such as `main.py`.

## OOP and SOLID
- Give each class one reason to change.
- Depend on abstractions, not concrete repositories or clients.
- Keep use cases framework-agnostic and explicit about inputs and outputs.
- Prefer small immutable domain value objects and constructor injection.
- Avoid global mutable state and hidden service locators.

## Engineering
- Use Python 3.12, type annotations, and docstrings for public APIs.
- Keep route handlers thin: validate transport data, call a use case, map the result.
- Raise domain/application exceptions and map them to HTTP responses at the API boundary.
- Add focused tests for domain rules, use cases, and API contracts.
- Run `ruff check .`, `mypy src`, and `pytest` before submitting changes.

## Database
- Use SQLAlchemy 2.x models in `app/models` and session wiring in `app/db`.
- Keep repository query and persistence logic in `app/repositories`.
- Manage schema changes with Alembic migrations under `migrations/versions`.
- Read `DATABASE_URL` from environment configuration; never commit credentials.
