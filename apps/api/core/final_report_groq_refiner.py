from __future__ import annotations

import json
import re
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

# Match prohibited vendor terms as WHOLE WORDS, not substrings. A naive substring
# check rejected legitimate forensic prose: "meta" matched "metadata"/"metallic",
# so every report with a metadata finding was wrongly refused. Word boundaries fix
# the false positives while still catching the standalone vendor names.
_PROHIBITED_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in PROHIBITED_WORDS) + r")\b",
    re.IGNORECASE,
)

# P0.4 — mandatory disclosures the refiner must never drop. The narrative model
# may improve wording, but a calibration / coverage / tool-failure disclosure that
# was in the signed deterministic baseline must always survive refinement. Any
# baseline reliability note matching this is re-injected after refinement.
_MANDATORY_DISCLOSURE_RE = re.compile(
    r"uncalibrated|calibration|could not be verified|not court-admissible|"
    r"must not be cited|coverage limitation|tool failure|did not complete",
    re.IGNORECASE,
)


def _is_mandatory_disclosure(note: Any) -> bool:
    return bool(_MANDATORY_DISCLOSURE_RE.search(str(note or "")))


# ── Post-generation numeric validation ───────────────────────────────────────
# The refiner is narrative-only: every percentage, confidence, and count in its
# output must already exist in the deterministic findings/tool data it was
# given. A number with no source is a fabrication → one corrective retry, then
# fall back to the deterministic text.
_NUMBER_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)")


def _allowed_numeric_values(payload: dict[str, Any]) -> set[float]:
    """Every number present in the deterministic input, plus fraction↔percent
    and rounding variants (0.82 ⇄ 82 ⇄ 82.0) so unit normalisation by the
    model is not treated as fabrication."""
    allowed: set[float] = set()
    blob = json.dumps(payload, default=str)
    for m in _NUMBER_RE.finditer(blob):
        try:
            v = float(m.group(1))
        except ValueError:  # pragma: no cover — regex guarantees float
            continue
        allowed.add(v)
        allowed.add(round(v))
        allowed.add(round(v, 2))
        if 0.0 <= v <= 1.0:
            allowed.add(round(v * 100))
            allowed.add(round(v * 100, 1))
        if v > 1.0:
            allowed.add(round(v / 100, 4))
    return allowed


def _claim_supported(value: float, allowed: set[float]) -> bool:
    tol = 0.011 if value <= 1.5 else 0.51
    return any(abs(value - a) <= tol for a in allowed)


def _unsupported_numeric_claims(parsed: dict[str, Any], allowed: set[float]) -> list[str]:
    """Numeric claims in the refined narrative absent from the input data."""
    texts: list[str] = []
    for sec in REQUIRED_SECTIONS:
        val = parsed.get(sec)
        if isinstance(val, list):
            texts.extend(str(x) for x in val)
        elif val:
            texts.append(str(val))
    unsupported: list[str] = []
    for text in texts:
        for m in _NUMBER_RE.finditer(text):
            try:
                v = float(m.group(1))
            except ValueError:  # pragma: no cover
                continue
            if not _claim_supported(v, allowed) and m.group(1) not in unsupported:
                unsupported.append(m.group(1))
    return unsupported

_SYSTEM_PROMPT = (
    "You are a forensic report editor. The arbiter has already determined the verdict, "
    "confidence, and all evidentiary findings. Your role is strictly narrative: improve "
    "clarity, precision, and professional register of the four provided fields.\n\n"
    "INVIOLABLE RULES:\n"
    "1. 'final_verdict' and 'confidence_score' are FIXED context set by the arbiter. "
    "Never change them, and do NOT include them as keys in your output — your output is "
    "ONLY the four narrative keys listed below.\n"
    "2. Do NOT invent tool names, findings, or metrics not present in the input.\n"
    "3. Do NOT mention any AI provider, model name, or vendor "
    "(Gemini, Groq, OpenAI, Cerebras, Llama, Claude, GPT, YOLO, CLIP, etc.).\n"
    "4. 'executive_summary' must be exactly 3–4 sentences. "
    "Keep the **verdict** and **confidence** bold markers where they appear.\n"
    "5. Every item in 'key_findings' must follow: "
    "`[Finding with metric] — [tool_name] ([confidence]%)`. "
    "The em-dash (—) is required. Do not reorder or remove items.\n"
    "6. 'reliability_notes' is a list of strings — preserve it as a list, and NEVER "
    "remove or weaken any calibration, coverage-limitation, or tool-failure disclosure; "
    "you may polish wording but the disclosure must remain.\n"
    "7. 'final_conclusion' is one sentence. Keep it concise.\n"
    "8. Return ONLY a JSON object with exactly these four keys: "
    "executive_summary, key_findings, reliability_notes, final_conclusion. "
    "No markdown fences, no extra keys, no commentary.\n"
)


async def refine_report_with_groq(
    deterministic_report: dict[str, Any],
    config: Settings,
    investigation_id: str = "",
) -> tuple[dict[str, Any], bool]:
    """Polish the 4 DTO-visible narrative fields with Groq.

    Returns the updated report dict and a success flag. Falls back to the
    deterministic report on any failure or validation rejection. When the
    refined text carries numeric claims absent from the deterministic input
    (post-generation numeric validation), ONE corrective retry is made before
    falling back.

    WS-6 #30: an *attempted* refinement that falls back (quota, 429, parse
    or validation rejection) increments `forensic_refiner_fallback_total` so
    operators can alert on silent narrative degradation. An intentional skip
    (LLM disabled / no key) is not counted — that is configuration, not
    degradation.
    """
    llm_client = LLMClient(config=config, use_arbiter_tier=True)
    if not (config.llm_enable_post_synthesis and config.llm_api_key and llm_client.is_available):
        logger.info("Skipping Groq report polish: LLM disabled or api key unavailable.")
        return deterministic_report, False

    # Per-investigation token budget: the refiner is the job the ~4800-token
    # reserve exists for (job="refiner" may consume into the reserve).
    if investigation_id:
        from core.quota_manager import get_investigation_budget

        estimated = len(json.dumps(deterministic_report, default=str)) // 8 + 800
        allowed, reason = await get_investigation_budget(investigation_id).try_consume(
            estimated, job="refiner"
        )
        if not allowed:
            logger.warning(f"Skipping Groq report polish: {reason}")
            return deterministic_report, False

    report, success, numeric_issues = await _attempt_refine(deterministic_report, llm_client)
    if not success and numeric_issues:
        # Post-generation numeric validation failed — retry ONCE with a
        # corrective instruction, then fall back to the deterministic text.
        corrective = (
            "CORRECTION: your previous draft cited numeric values that do not "
            f"appear in the input data: {', '.join(numeric_issues[:8])}. Every "
            "percentage, confidence, and count in your output MUST appear in the "
            "input fields verbatim. Rewrite without inventing or altering numbers."
        )
        logger.warning(
            "Groq refiner produced unsupported numeric claims — retrying once with correction.",
            unsupported=numeric_issues[:8],
        )
        report, success, _ = await _attempt_refine(
            deterministic_report, llm_client, corrective_note=corrective
        )
    if not success:
        try:
            from api.routes.metrics import increment_refiner_fallback

            increment_refiner_fallback()
        except Exception:  # noqa: S110 - metrics must never break report generation
            pass
    return report, success


async def _attempt_refine(
    deterministic_report: dict[str, Any],
    llm_client: LLMClient,
    corrective_note: str = "",
) -> tuple[dict[str, Any], bool, list[str]]:
    """One refinement attempt. Returns (report, success, unsupported_numbers).

    `unsupported_numbers` is non-empty only when the attempt failed solely on
    the post-generation numeric validation — the caller uses it to drive the
    single corrective retry.
    """
    # Narrow input — only send the sections Groq is allowed to touch.
    input_payload = {
        "final_verdict": deterministic_report.get("final_verdict"),
        "confidence_score": deterministic_report.get("confidence_score"),
        "executive_summary": deterministic_report.get("executive_summary"),
        "key_findings": deterministic_report.get("key_findings"),
        "reliability_notes": deterministic_report.get("reliability_notes"),
        "final_conclusion": deterministic_report.get("final_conclusion"),
    }

    system_prompt = _SYSTEM_PROMPT + (f"\n{corrective_note}\n" if corrective_note else "")

    try:
        raw_response = await llm_client.generate_synthesis(
            system_prompt=system_prompt,
            # The narrowed deterministic report IS the user content the model
            # refines. Omitting it raised "generate_synthesis() missing 1 required
            # positional argument: 'user_content'" on every call, so the refiner
            # always crashed and the verbose deterministic narrative shipped unrefined.
            user_content=json.dumps(input_payload, default=str),
            # The refiner re-emits the full report (executive summary, key findings,
            # reliability notes, conclusion) as one JSON object. 800 tokens was too
            # tight: on a real report the model hit the completion limit mid-JSON and
            # Groq rejected the whole call with `json_validate_failed`, silently
            # dropping the narrative to the deterministic template. Give it room.
            max_tokens=2048,
            timeout_override=30.0,
            json_mode=True,
            priority="critical",
        )
        if not raw_response:
            logger.warning("Groq report refiner returned empty response.")
            return deterministic_report, False, []

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

        # Verdict/confidence are FIXED by the arbiter and are NOT part of the
        # refiner's output contract (system rule #8 asks for only the 4 narrative
        # keys), so the model legitimately OMITS them. The merge below always
        # preserves the deterministic verdict, so an omission is harmless — reject
        # only an explicit, DIFFERING override. (Previously a `None != verdict`
        # comparison rejected every report, wasting the Groq call and always
        # falling back to the unrefined deterministic narrative.)
        rv = parsed.get("final_verdict")
        if rv is not None and rv != deterministic_report.get("final_verdict"):
            logger.warning("Groq refiner rejected: modified final_verdict.")
            return deterministic_report, False, []
        rc = parsed.get("confidence_score")
        if rc is not None and rc != deterministic_report.get("confidence_score"):
            logger.warning("Groq refiner rejected: modified confidence_score.")
            return deterministic_report, False, []

        # All 4 required sections must be present and clean
        for sec in REQUIRED_SECTIONS:
            sec_val = parsed.get(sec)
            if not sec_val:
                logger.warning(f"Groq refiner rejected: missing section `{sec}`.")
                return deterministic_report, False, []
            text_to_check = (
                " ".join(str(x) for x in sec_val)
                if isinstance(sec_val, list)
                else str(sec_val)
            )
            _m = _PROHIBITED_RE.search(text_to_check)
            if _m:
                logger.warning(f"Groq refiner rejected: prohibited vendor term `{_m.group(0)}` in `{sec}`.")
                return deterministic_report, False, []

        # key_findings must keep the em-dash format
        refined_kfs = parsed.get("key_findings")
        if not isinstance(refined_kfs, list) or not refined_kfs:
            logger.warning("Groq refiner rejected: key_findings is not a non-empty list.")
            return deterministic_report, False, []
        for kf in refined_kfs:
            if " — " not in str(kf):
                logger.warning(f"Groq refiner rejected: key finding lacks em-dash format: {kf!r}")
                return deterministic_report, False, []

        # Post-generation numeric validation: every percentage / confidence /
        # count in the refined narrative must appear in the findings/tool data
        # passed in. An unsupported number is a fabrication — return the list so
        # the caller can issue the single corrective retry.
        _allowed_numbers = _allowed_numeric_values(input_payload)
        _unsupported = _unsupported_numeric_claims(parsed, _allowed_numbers)
        if _unsupported:
            logger.warning(
                "Groq refiner rejected: numeric claims not present in input data.",
                unsupported=_unsupported[:8],
            )
            return deterministic_report, False, _unsupported

        # P0.4 — post-refinement tool-existence guard: the deterministic baseline
        # only cites tools that actually ran, so a refined finding citing a tool
        # absent from the baseline is a fabrication. Reject rather than ship it.
        def _cited_tools(items: Any) -> set[str]:
            out: set[str] = set()
            for it in items or []:
                m = re.search(r"—\s*([A-Za-z0-9 _/().,-]+?)\s*\(", str(it))
                if m:
                    out.add(re.sub(r"[^a-z0-9]", "", m.group(1).lower()))
            return out

        _baseline_tools = _cited_tools(deterministic_report.get("key_findings"))
        if not _cited_tools(refined_kfs).issubset(_baseline_tools):
            logger.warning("Groq refiner rejected: refined key findings cite a tool absent from the baseline.")
            return deterministic_report, False, []

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

        # P0.4 / append-only contract: reliability_notes may be EXTENDED by the
        # refiner but never reduced or rewritten away. Every baseline note that
        # is missing verbatim from the refined list is re-injected (mandatory
        # calibration/coverage/failure disclosures go to the front; the rest are
        # appended). The deterministic-narrative note is the single intentional
        # swap (replaced by the Groq-assisted note above).
        _orig_notes = list(deterministic_report.get("reliability_notes") or [])
        _refined_set = {str(n).strip().lower() for n in reliability_notes}
        for _note in _orig_notes:
            if str(_note) == det_note:
                continue  # intentionally swapped for groq_note
            if str(_note).strip().lower() not in _refined_set:
                if _is_mandatory_disclosure(_note):
                    reliability_notes.insert(0, _note)
                else:
                    reliability_notes.append(_note)
        final_report["reliability_notes"] = reliability_notes

        logger.info("Successfully refined 4 narrative sections with Groq.")
        return final_report, True, []

    except Exception as e:
        logger.warning(f"Groq report refiner failed ({e}). Falling back to deterministic.")
        return deterministic_report, False, []
