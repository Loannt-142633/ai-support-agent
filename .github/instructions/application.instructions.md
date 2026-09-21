---
applyTo: "app/services/**/*.py"
---
# Application Rules

- Implement one business workflow per use-case class.
- Inject repositories, clocks, and external services through constructor parameters.
- Do not import FastAPI or expose transport-specific request/response models.
- Coordinate domain objects; do not duplicate domain invariants here.
- Return domain results or application DTOs that presentation can map explicitly.
