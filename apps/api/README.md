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

## Architecture (layers)

The backend is organized as layers, top (request edge) to bottom (data):

| Layer | Path | Responsibility |
| --- | --- | --- |
| HTTP / API edge | `api/` (`routes/`, `middleware/`, `lifespan.py`) | FastAPI routes, CSRF/CSP/rate-limit/metrics middleware, app lifespan + startup gating |
| Orchestration | `orchestration/` | Investigation lifecycle, Redis work queue, worker loop, session manager, agent factory |
| Agents | `agents/` | The 5 specialist agents (Image, Audio, Object, Video, Metadata) + the Council Arbiter; shared `mixins/` (context, investigation, memory, reflection, synthesis) |
| Domain / services | `core/` (+ `core/handlers/`) | Synthesis, calibration, cross-modal fusion, chain-of-custody, humanization, config, Gemini/LLM clients |
| Tools / ML | `tools/` (+ `tools/audio/`, `tools/ml_tools/`) | Forensic tools + ML detectors. `tools/ml_tools/trufor_pkg/` is vendored upstream (excluded from lint) |
| Persistence | `core/persistence/` | Postgres (asyncpg), Redis, Qdrant, evidence store |
| Config | `config/` (`models.lock.json`, `task_tool_overrides.yaml`) + `core/config.py` | Settings, model pins, per-task tool overrides |
| Migrations / ops | `alembic/`, `scripts/` | Schema migrations + operational scripts |

## Quality gates

The backend is linted with **ruff** and type-checked with **pyright** (both configured in `pyproject.toml`), and tested with **pytest**:

```bash
python -m ruff check .          # lint (clean)
python -m pyright               # type-check (0 errors)
python -m pytest -q             # default suite (excludes requires_docker/network/ml)
```

Vendored ML code (`tools/ml_tools/trufor_pkg`) is excluded from ruff. Intentional
patterns (UPPER_CASE in-function constant tables, best-effort `try/except` guards,
deferred imports, non-crypto retry jitter) are acknowledged via `per-file-ignores`
in `pyproject.toml` rather than scattered inline suppressions.

## Tests

- `tests/`: unit, contract, integration, forensics, and system suites.
- Markers gate heavyweight tests: `requires_docker`, `requires_network`,
  `requires_ml`, `requires_services` (see `pyproject.toml`).
- Run the full local suite via `bash scripts/verify_project.sh`.