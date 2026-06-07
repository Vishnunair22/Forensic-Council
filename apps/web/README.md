# Forensic Council Frontend

Next.js 15 / React 19 frontend for the Forensic Council multi-agent forensic evidence analysis system.

## Setup & Development
The primary entry points for development are the root wrapper scripts:
- To boot the entire stack (backend, worker, frontend, and infra) in Docker dev mode:
  ```bash
  bash scripts/dev.sh
  ```
- To run tests:
  ```bash
  bash scripts/verify_project.sh
  ```

For detailed setup instructions, host-run options, and workflow commands, please refer to the root [README.md](../../README.md) and the [Docker Build & Lifecycle Guide](../../infra/DOCKER_BUILD.md).

The UI follows a single, mechanically-enforced design system — see
[FRONTEND_DESIGN_SYSTEM.md](./FRONTEND_DESIGN_SYSTEM.md) (Precision Frosted Glass:
surfaces, motion, typography, a11y, and the ESLint rules that gate them).

## Subdirectory Structure
- `src/app/`: Next.js App Router pages, layouts, and API proxy/auth routes.
- `src/components/`: Modular UI, evidence workflow, and result report components.
- `src/hooks/`: React hooks for API interaction, session storage, and state.
- `src/lib/`: API clients, validation schemas, and local storage helpers.
- `src/types/`: TypeScript declarations.
- `tests/`: Unit, accessibility, component, and Playwright E2E suites.