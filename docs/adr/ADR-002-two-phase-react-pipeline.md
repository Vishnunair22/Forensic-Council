# ADR-002: Two-Phase ReAct Pipeline

## Status

Accepted

## Context

Forensic analysis tools fall into two categories:
1. **Fast tools** (ELA, EXIF, hash) that complete in 1-5 seconds with no ML model download.
2. **Heavy tools** (PRNU, Gemini vision, voice clone detection) that require 15-120 seconds and may download 100 MB+ models on first run.

Running all tools in a single pass would force the user to wait 3-5 minutes before seeing any results.

## Decision

Split the pipeline into two phases:
1. **Initial pass**: Run fast tools concurrently, stream results to frontend immediately.
2. **Deep pass**: Run heavy ML tools in background after user confirms, with live progress updates.

## Consequences

- Users see actionable initial findings within 30-60 seconds.
- Deep analysis is opt-in — users can accept initial results and skip the heavy pass.
- Agent working memory is namespaced (`agent_id` vs `agent_id_deep`) to prevent cross-contamination.
- Cross-agent Gemini context injection (Agent1 → Agent3/Agent5) requires careful asyncio.Event coordination.
