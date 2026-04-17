# Cross-Service Integration Tests

Backend-specific integration tests live in `apps/api/tests/integration/`.

This directory is reserved for **cross-service** integration tests that span
multiple applications (e.g., API + Web + Docker stack). See `../e2e/` for
end-to-end flows and `../connectivity/` for live stack health checks.
