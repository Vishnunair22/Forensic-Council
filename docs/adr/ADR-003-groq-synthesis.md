# ADR-003: Groq for Narrative Synthesis

## Status

Accepted

## Context

After all agents complete, the Council Arbiter needs to generate:
1. A structured verdict summary (verdict sentence, key findings, reliability note)
2. Per-agent analysis narratives
3. An executive summary
4. An uncertainty statement

Options for LLM synthesis:
- **Groq Llama 3.3 70B**: Free tier available, high inference speed, sufficient quality for structured forensic narratives.
- **Google Gemini 2.5 Flash**: Fast, multimodal, and used for vision-audio grounding.

## Decision

Use Groq with Llama 3.3 70B for all post-analysis synthesis tasks, with Gemini as a fallback.

## Consequences

- Synthesis completes in 3-5 seconds vs other providers.
- Free tier is sufficient for development and low-volume production.
- Template/grounded fallbacks are maintained for when Groq is unreachable (3s health check before parallel calls).
- The `llm_provider` config allows switching to Gemini or disabling synthesis without code changes.
