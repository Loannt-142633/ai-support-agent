---
applyTo: "app/db/**/*.py,app/models/**/*.py,app/repositories/**/*.py,migrations/**/*.py"
---
# Database Rules

- Use PostgreSQL in all runtime and deployment environments.
- Use SQLAlchemy 2.x models and typed `Mapped` columns.
- Keep engine and session lifecycle in `app/db`; routes must not create sessions directly.
- Keep SQL queries and persistence operations inside repositories.
- Services may coordinate repositories but must not import SQLAlchemy query APIs.
- Use Alembic migrations for schema changes; do not call `Base.metadata.create_all` in application startup.
- Keep foreign keys, indexes, uniqueness constraints, and cascade behavior explicit in models or migrations.
- Never commit credentials; use `DATABASE_URL` from environment configuration.
