---
applyTo: "app/services/**/*.py"
---
# Infrastructure Rules

- Implement interfaces defined by domain or application layers.
- Keep persistence, HTTP clients, queues, and SDK details inside adapters.
- Map external data to domain objects at the boundary.
- Make adapters replaceable and constructor-configurable.
- Do not leak ORM models or vendor exceptions into use cases.
- Keep SQLAlchemy models and sessions in `app/models` and `app/db`.
- Repositories own query construction and transaction boundaries; services do not query the database directly.
- Use Alembic migrations for schema changes. Do not rely on `create_all` in production startup.
- Database configuration must come from environment-backed settings, never hard-coded credentials.
