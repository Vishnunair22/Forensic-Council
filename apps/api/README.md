# Forensic Council Backend

FastAPI backend for the Forensic Council multi-agent forensic evidence analysis system.

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

## Subdirectory Structure
- `api/`: FastAPI routers, controllers, and schemas.
- `agents/`: AI forensic agents (Image, Audio, Object, Video, Metadata) and the Arbiter.
- `config/`: System tool overrides and locked model definitions.
- `core/`: Core utilities (auth, memory, signing, custody logging, provider limits).
- `orchestration/`: Queue, session manager, pipeline orchestration, and task loop.
- `tools/`: Subprocess-based ML models, OCR, and file metadata extractors.
- `tests/`: Extensive unit, contract, integration, and system test suites.