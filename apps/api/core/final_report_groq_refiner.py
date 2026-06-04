from __future__ import annotations

import json
from typing import Any

from core.config import Settings
from core.llm_client import LLMClient
from core.structured_logging import get_logger

logger = get_logger(__name__)

# Only the fields that flow through the DTO and are rendered in the result page.
# Refining the 7 backend-only sections (methodology, integrity_assessment, etc.)
# wastes ~60% of quota on text no user ever sees.
REQUIRED_SECTIONS = [
    "executive_summary",
    "key_findings",
    "reliability_notes",
    "final_conclusion",
]

# Blacklist of prohibited vendor/model phrases to ensure report neutrality.
PROHIBITED_WORDS = [
    "gemini", "groq", "cerebras", "openai", "llama", "google", "meta", "gpt-", "claude",
    "llm assisted", "llm-assisted",
]

_SYSTEM_PROMPT = (
    "You are a forensic report editor. The arbiter has already determined the verdict, "
    "confidence, and all evidentiary findings. Your role is strictly narrative: improve "
    "clarity, precision, and professional register of the four provided fields.\n\n"
    "INVIOLABLE RULES:\n"
    "1. Do NOT change 'final_verdict' or 'confidence_score' — echo them verbatim.\n"
    "2. Do NOT invent tool names, findings, or metrics not present in the input.\n"
    "3. Do NOT mention any AI provider, model name, or vendor "
    "(Gemini, Groq, OpenAI, Cerebras, Llama, Claude, GPT, YOLO, CLIP, etc.).\n"
    "4. 'executive_summary' must be exactly 3–4 sentences. "
    "Keep the **verdict** and **confidence** bold markers where they appear.\n"
    "5. Every item in 'key_findings' must follow: "
    "`[Finding with metric] — [tool_name] ([confidence]%)`. "
    "The em-dash (—) is required. Do not reorder or remove items.\n"
    "6. 'reliability_notes' is a list of strings — preserve it as a list.\n"
    "7. 'final_conclusion' is one sentence. Keep it concise.\n"
    "8. Return ONLY a JSON object with exactly these four keys: "
    "executive_summary, key_findings, reliability_notes, final_conclusion. "
    "No markdown fences, no extra keys, no commentary.\n"
)


async def refine_report_with_groq(
    deterministic_report: dict[str, Any],
    config: Settings,
) -> tuple[dict[str, Any], bool]:
    """Polish the 4 DTO-visible narrative fields with Groq.

    Returns the updated report dict and a success flag. Falls back to the
    deterministic report on any failure or validation rejection.
    """
    llm_client = LLMClient(config=config, use_arbiter_tier=True)
    if not (config.llm_enable_post_synthesis and config.llm_api_key and llm_client.is_available):
        logger.info("Skipping Groq report polish: LLM disabled or api key unavailable.")
        return deterministic_report, False

    # Narrow input — only send the sections Groq is allowed to touch.
    input_payload = {
        "final_verdict": deterministic_report.get("final_verdict"),
        "confidence_score": deterministic_report.get("confidence_score"),
        "executive_summary": deterministic_report.get("executive_summary"),
        "key_findings": deterministic_report.get("key_findings"),
        "reliability_notes": deterministic_report.get("reliability_notes"),
        "final_conclusion": deterministic_report.get("final_conclusion"),
    }

    try:
        raw_response = await llm_client.generate_synthesis(
            system_prompt=_SYSTEM_PROMPT,
            user_content=json.dumps(input_payload, indent=2, default=str),
            max_tokens=800,
            timeout_override=30.0,
            json_mode=True,
            priority="critical",
        )
        if not raw_response:
            logger.warning("Groq report refiner returned empty response.")
            return deterministic_report, False

        cleaned_resp = raw_response.strip()
        if cleaned_resp.startswith("```"):
            lines = cleaned_resp.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned_resp = "\n".join(lines).strip()

        parsed = json.loads(cleaned_resp)

        # ── Validation ────────────────────────────────────────────────────────

        # Verdict and confidence must be unchanged
        if parsed.get("final_verdict") != deterministic_report.get("final_verdict"):
            logger.warning("Groq refiner rejected: modified final_verdict.")
            return deterministic_report, False
        if parsed.get("confidence_score") != deterministic_report.get("confidence_score"):
            logger.warning("Groq refiner rejected: modified confidence_score.")
            return deterministic_report, False

        # All 4 required sections must be present and clean
        for sec in REQUIRED_SECTIONS:
            sec_val = parsed.get(sec)
            if not sec_val:
                logger.warning(f"Groq refiner rejected: missing section `{sec}`.")
                return deterministic_report, False
            text_to_check = (
                " ".join(str(x) for x in sec_val)
                if isinstance(sec_val, list)
                else str(sec_val)
            ).lower()
            for word in PROHIBITED_WORDS:
                if word in text_to_check:
                    logger.warning(f"Groq refiner rejected: prohibited word `{word}` in `{sec}`.")
                    return deterministic_report, False

        # key_findings must keep the em-dash format
        refined_kfs = parsed.get("key_findings")
        if not isinstance(refined_kfs, list) or not refined_kfs:
            logger.warning("Groq refiner rejected: key_findings is not a non-empty list.")
            return deterministic_report, False
        for kf in refined_kfs:
            if " — " not in str(kf):
                logger.warning(f"Groq refiner rejected: key finding lacks em-dash format: {kf!r}")
                return deterministic_report, False

        # ── Merge only the 4 refined fields ──────────────────────────────────
        final_report = dict(deterministic_report)
        for sec in REQUIRED_SECTIONS:
            final_report[sec] = parsed[sec]

        # Swap deterministic reliability note for the Groq-assisted one
        reliability_notes = list(final_report.get("reliability_notes") or [])
        det_note = (
            "Reliability note: Final report narrative was generated deterministically from "
            "local tool findings and arbiter deliberation. No external text model was used."
        )
        if det_note in reliability_notes:
            reliability_notes.remove(det_note)
        groq_note = (
            "Reliability note: Final narrative cohesion was assisted by an external text model. "
            "The verdict, confidence, and evidentiary findings were computed by the arbiter "
            "from grounded tool outputs."
        )
        if groq_note not in reliability_notes:
            reliability_notes.append(groq_note)
        final_report["reliability_notes"] = reliability_notes

        logger.info("Successfully refined 4 narrative sections with Groq.")
        return final_report, True

    except Exception as e:
        logger.warning(f"Groq report refiner failed ({e}). Falling back to deterministic.")
        return deterministic_report, False
