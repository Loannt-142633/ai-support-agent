---
applyTo: "app/api/**/*.py"
---
# Presentation Rules

- Keep FastAPI routes thin and delegate business behavior to use cases.
- Use Pydantic models only for transport validation and serialization.
- Translate application/domain errors into stable HTTP responses here.
- Wire dependencies explicitly through FastAPI dependency providers.
- Keep route modules organized by resource and version APIs when they become public.
