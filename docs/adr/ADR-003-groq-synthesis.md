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
- **OpenAI GPT-4o**: High quality but expensive ($2.50/1M input tokens) and slower (~5s latency).
- **Anthropic Claude 3.5 Sonnet**: Strong reasoning but limited free tier and higher latency.
- **Groq Llama 3.3 70B**: Free tier available, ~200 tokens/s inference speed, sufficient quality for structured forensic narratives.

## Decision

Use Groq with Llama 3.3 70B for all post-analysis synthesis tasks.

## Consequences

- Synthesis completes in 3-5 seconds vs 10-30 seconds with other providers.
- Free tier is sufficient for development and low-volume production.
- Template fallbacks are maintained for when Groq is unreachable (3s health check before parallel calls).
- The `llm_provider` config allows switching to OpenAI or Anthropic without code changes.

