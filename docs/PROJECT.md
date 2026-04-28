# Project: Forensic Council

The **Forensic Council** is a mission-critical, court-grade digital evidence analysis platform. It leverages a multi-agent orchestration architecture to validate the authenticity of images, audio, and video evidence against sophisticated AI manipulation and deepfakes.

## Core Tech Stack
- **Frontend**: Next.js (App Router), Framer Motion, TailwindCSS (for secondary utilities), Lucide, Web Audio API (Synthesized HUD sounds).
- **Backend**: FastAPI, asyncio, ReAct Agent Loops.
- **AI/ML Engine**: Groq (Llama 3.3 for synthesis), Google Gemini 2.x (Multi-modal forensic analysis), YOLOv8 (Object detection).
- **Infrastructure**: Redis (Working Memory), Qdrant (Episodic Memory), PostgreSQL (Custody Log & Sessions).

## Forensic Guardrails
1. **Chain of Custody**: Every tool execution must be logged to the Custody Log with a cryptographic signature.
2. **Neutrality**: Agents must report raw tool observations before forming a synthesis.
3. **Arbiter Deliberation**: Contradictions between agents trigger a "Challenge Loop" or escalate to a human-in-the-loop Tribunal.
4. **Court-Defensible Output**: Every finding must include a `court_statement` that can be included in a legal report.

## Milestone History
- ✅ **v1.4.0 Production Hardening** — Shipped 2026-04-16. (Phases 1-4: Structural, Functional, Quality, Improvements).
  - *Key Outcome:* Achieved forensic-grade observability, hardware-efficient resource handling, and 24/24 UI excellence.

## Next Milestone Goals
- Transitioning to **Field Ready** capabilities.
- Docker-Compose optimization for air-gapped environments.
- Tribunal HITL Interface refinement.
- Final 2026 Standards Compliance Audit.

---
*Last updated: 2026-04-16 after v1.4.0 milestone*
