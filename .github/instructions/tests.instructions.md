---
applyTo: "tests/**/*.py"
---
# Test Rules

- Keep unit tests isolated from frameworks and external services.
- Use in-memory adapters or fakes for application use-case tests.
- Test API behavior through the public HTTP contract.
- Name tests by observable behavior, not implementation details.
- Add regression coverage when changing a domain invariant or boundary contract.
