# Architecture Decision Records (ADRs)

## ADR 1: LangGraph over Raw Asyncio for Agent Orchestration
*   **Date**: 2026-02-15
*   **Context**: Building a stable multi-agent ReAct loop.
*   **Decision**: Adopt LangGraph.
*   **Rationale**: While we initially built custom `asyncio` loops, managing cyclic agent reasoning (Thought → Action → Observation → Thought) became fragile. LangGraph treats agent state as a directional graph, giving us native cycle detection, structured state checkpoints, and easier integration with our WebSocket streaming pipeline.

## ADR 2: Qdrant over Pinecone/Milvus for Vector Search
*   **Date**: 2026-02-18
*   **Context**: Need a vector database for historical similarity matching.
*   **Decision**: Use Qdrant locally.
*   **Rationale**: The Forensic Council handles highly sensitive, frequently classified media. Cloud dependencies (Pinecone) violate our data-residency constraints. Compared to Milvus, Qdrant relies on Rust, is significantly lighter to deploy via Docker Compose, and doesn't require complex distributed dependencies (like etcd/MinIO) for a single-node deployment.

## ADR 3: Subprocess ML over Native Python Threads
*   **Date**: 2026-02-22
*   **Context**: Integrating heavy ML (IsolationForest, GaussianMixtures, Fourier transforms) into the FastAPI backend.
*   **Decision**: Decouple completely to CLI subprocesses via `asyncio.create_subprocess_exec`.
*   **Rationale**: Python's Global Interpreter Lock (GIL) and event-loop blocking model mean that running a 30-second `librosa` audio calculation natively starves the FastAPI server, dropping all active WebSocket connections. Spawning isolated subprocesses ensures the main web server remains responsive, and OS-level memory can be freed immediately when the CLI script terminates.

## ADR 4: Sequential vs Parallel Agent Execution
*   **Date**: 2026-02-28
*   **Context**: Processing a single payload through 5 agents.
*   **Decision**: Enforce sequential execution.
*   **Rationale**: Parallelizing 5 LLM chains and 5 heavy ML subprocesses simultaneously on typical analyst hardware caused severe out-of-memory (OOM) crashes and disjointed UX. Sequential execution slows down the total *wall-clock* time but drastically improves system stability and provides a linear, readable stream of text for the UI.

## ADR 5: GitHub Actions for CI/CD
*   **Date**: 2026-03-11
*   **Context**: No automated gate existed; tests were never run on push.
*   **Decision**: Add `.github/workflows/ci.yml` with backend + frontend lint/type-check/build jobs, dependency audits, and an integration smoke test gated to `main` pushes.
*   **Rationale**: Forensic evidence tooling has a high correctness bar. Catching regressions in the signing pipeline or auth layer before merge is non-negotiable. The smoke test runs the full Docker stack against a live backend to verify `/health` and auth rejection without requiring real ML models (`LLM_PROVIDER=none`).

## ADR 6: Redis-Backed Rate Limiting with In-Process Fallback
*   **Date**: 2026-03-11
*   **Context**: A single authenticated user could submit unlimited investigation jobs, exhausting memory and CPU.
*   **Decision**: Redis `INCR`/`EXPIRE` counters for per-user investigation rate limits and per-IP login attempt tracking; in-process dict as fallback when Redis is unreachable.
*   **Rationale**: Pure in-process counters reset on restart and are wrong across replicas. Pure Redis counters fail if Redis is momentarily unavailable. The dual-layer approach gives correct multi-replica behaviour in steady state while degrading gracefully to single-node accuracy during Redis outages rather than blocking all requests.
