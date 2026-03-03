# System Architecture

The Forensic Council is a distributed, multi-agent AI framework designed for cryptographic evidence analysis. 

## 1. High-Level Data Flow

The system processes evidence in a deterministic pipeline to ensure auditability:

1.  **Ingestion & Validation**: Client uploads evidence via Next.js frontend to the FastAPI `/investigate` endpoint. File hashing secures the original state.
2.  **Working Memory Init**: A session is created in **Redis**. This memory acts as the scratchpad for agent thoughts and actions.
3.  **Sequential Agent Execution**: The 5 specialized agents are invoked sequentially (Image → Audio → Object → Video → Metadata). We prioritize sequential execution over parallel to maintain stable frontend WebSocket streaming and prevent connection saturation.
4.  **ReAct Loop & ML Delegation**: Inside each agent, an LLM drives a Reason-and-Act (ReAct) loop. Heavy lifting (e.g., Fourier transforms, Isolation Forests) is pushed out of the event loop to Python CLI subprocesses (`backend/scripts/ml_tools/`).
5.  **Arbiter Synthesis**: Once all agents complete, the Council Arbiter cross-references findings from Redis. Conflicting confident findings trigger the **HITL (Human-In-The-Loop)** webhook.
6.  **Cryptographic Signing**: The final report (including Arbiter verdict, all agent JSON traces, and timestamps) is hashed (SHA-256) and signed (ECDSA) using the `SIGNING_KEY`.
7.  **Custody Logging**: The signed payload is written to **PostgreSQL**.

## 2. Infrastructure Components

We rely on three separate data stores, each chosen for a precise architectural reason:

### Redis (Working Memory / State)
*   **Why**: State management in a distributed system requires ultra-fast reads/writes. Tracking intermediate agent `THOUGHT` and `ACTION` blocks in Postgres would cause extreme IO bottlenecking.
*   **Usage**: Rate-limiting, active session state, short-lived WebSockets pub/sub, agent lock coordination. Configured with a strict 24-hour TTL (`ex=86400`) to prevent memory leaks.

### PostgreSQL (The Ledger)
*   **Why**: Evidence custody demands ACID compliance. Relational integrity is required to link an `InvestigationSession` to multiple `AgentFinding` records and the final cryptographically signed `Report`.
*   **Usage**: Long-term storage. Only final, immutable results are written here.

### Qdrant (Vector / Similarity)
*   **Why**: Standard databases cannot perform similarity matching on ML embeddings efficiently. Qdrant is optimized in Rust for local dense vector operations without relying on external APIs.
*   **Usage**: Used by agents (specifically Object and Evidence correlation) to query historical anomalies. Determines if a new piece of evidence closely matches a previously debunked fake.

## 3. Communication

*   **REST API**: Used only for synchronous commands (Uploading, Polling Final States, Submitting HITL decisions).
*   **WebSockets**: Unidirectional stream from Backend → Frontend pushing internal ReAct cognitive traces. Reduces UI perceived latency during 2-5 minute investigations.
