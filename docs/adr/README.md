# Architecture Decision Records (ADRs)

Index of all architectural decisions for the Forensic Council project.

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [ADR-001](ADR-001-qdrant-vector-memory.md) | Qdrant for Vector Memory | Accepted | 2025-01 |
| [ADR-002](ADR-002-two-phase-react-pipeline.md) | Two-Phase ReAct Pipeline | Accepted | 2025-01 |
| [ADR-003](ADR-003-groq-synthesis.md) | Groq for Narrative Synthesis | Accepted | 2025-02 |
| [ADR-004](ADR-004-cpu-only-torch.md) | CPU-Only PyTorch in Docker | Accepted | 2025-02 |
| [ADR-005](ADR-005-bcrypt-shim-retention.md) | bcrypt Shim Retention | Accepted | 2026-05 |

## Creating a New ADR

1. Copy the template below into a new file `ADR-NNN-short-title.md`
2. Fill in all sections: Title, Status, Date, Context, Decision, Consequences
3. Link from this index

### ADR Template

```markdown
# ADR-NNN: Title

## Status
Proposed | Accepted | Deprecated | Superseded

## Date
YYYY-MM-DD

## Context
What is the issue that is triggering this decision?

## Decision
What is the change being made?

## Consequences
What becomes easier or harder as a result of this decision?
```

## ADR Numbering Rules

- Assign the next sequential number based on the highest existing ADR
- Status values: `Proposed` → `Accepted` → `Deprecated` / `Superseded`
- Update this index when a new ADR is added or status changes
- Superseded ADRs should include a link to the replacement in their body