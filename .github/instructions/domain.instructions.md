---
applyTo: "app/services/**/*.py"
---
# Domain Rules

- Keep business concepts independent from all frameworks and I/O.
- Model invariants in entities and value objects, not in route handlers.
- Use `dataclass(frozen=True=True)` where identity and mutation are not required.
- Define repository contracts here when the business use case owns the abstraction.
- Domain exceptions should describe business failures without HTTP status codes.
