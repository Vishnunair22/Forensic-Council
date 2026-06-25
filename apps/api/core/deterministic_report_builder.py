from __future__ import annotations

import re
from typing import Any

from core.arbiter_deliberation import ArbiterDeliberationResult
from core.calibration import (
    CalibrationStatus,
    get_calibration_layer,
    is_system_uncalibrated,
)
from core.capability_manifest import (
    build_manifest_from_coverage,
    get_current_manifest,
    truthful_tool_display,
)
from core.finding_humanizer import CONTEXT_ONLY_TOOLS
from core.per_agent_synthesis import AgentSynthesisOutput, _fuzzy_tool_alias
from core.structured_logging import get_logger

logger = get_logger(__name__)


# Narrative sections of the deterministic report, used for the reproducibility
# block. The Groq refiner only ever rewrites _LLM_REFINABLE_SECTIONS (see
# core.final_report_groq_refiner); everything else stays deterministic.
_REPORT_SECTIONS = (
    "executive_summary",
    "methodology",
    "methodology_detail",
    "agent_deliberation_summary",
    "key_findings",
    "integrity_assessment",
    "object_scene_context",
    "metadata_and_provenance",
    "limitations",
    "reliability_notes",
    "likelihood_assessment",
    "final_conclusion",
)
_LLM_REFINABLE_SECTIONS = (
    "executive_summary",
    "key_findings",
    "reliability_notes",
    "final_conclusion",
)


def _mirror_manipulation_probability(mapped_verdict: str, confidence: float) -> float:
    """Deterministic mirror of agents.arbiter._manipulation_probability.

    Duplicated here (rather than imported) because core must not import the
    agents layer; keep both in sync if the banding ever changes.
    """
    v = (mapped_verdict or "").upper()
    c = max(0.0, min(1.0, confidence))
    if v == "MANIPULATED":
        return round(max(0.75, c), 3)
    if v == "SUSPICIOUS":
        return round(0.50 + 0.25 * c, 3)
    if v == "AUTHENTIC":
        return round(0.15 * (1.0 - c), 3)
    return 0.5


def _likelihood_assessment(manipulation_probability: float) -> str:
    """Phase 3.2 — deterministic qualitative likelihood-ratio banding for the
    computed manipulation probability, with an explicit base-rate caveat."""
    p = max(0.0, min(1.0, float(manipulation_probability)))
    if p >= 0.90:
        band = "strong support for manipulation over authentic capture"
    elif p >= 0.75:
        band = "moderate support for manipulation over authentic capture"
    elif p >= 0.55:
        band = "limited support for manipulation over authentic capture"
    else:
        band = (
            "no net support for manipulation over authentic capture "
            "(the observations are at least as consistent with authentic capture)"
        )
    return (
        f"Expressed as a likelihood statement, the computed manipulation probability of "
        f"{p:.2f} provides {band}. This statement compares the observations under the "
        "manipulation and authentic-capture hypotheses only; it does NOT incorporate "
        "source base rates (the prior prevalence of manipulated media in the submitting "
        "context), which a fact-finder must supply separately."
    )


# Mirror of the result page's KeyFindings danger heuristic (KeyFindings.tsx) so the
# report-level key-finding order agrees with how the UI classifies each line.
_KF_MANIP_RE = re.compile(
    r"tamper|manipulat|fabricat|synthetic|forged|splic|composit|confirmed anomaly|"
    r"malware|payload|deepfake|ai.generat|artificially generated|generated image",
    re.IGNORECASE,
)
_KF_CONSISTENT_MANIP_RE = re.compile(
    r"consistent with (?:a |an )?(?:composit|splic|manipulat|tamper|forg|generat|synthetic|cloned|fabricat)",
    re.IGNORECASE,
)
_KF_NEGATED_RE = re.compile(
    r"\b(no|not|without|free of|negative for|consistent with|unmodified|authentic|coherent)\b|absen",
    re.IGNORECASE,
)


def _kf_asserts_manipulation(kf: str) -> bool:
    """True when a key finding ASSERTS a manipulation signal (so it should lead the
    list); False for clean/negated lines. Classifies the STATEMENT only — the part
    before the ` — Tool (NN%)` attribution — so a tool name like "AI-Generation
    Detection" on a clean line does not trip the manipulation keywords. Used only for
    stable material-first ordering, never to drop a finding.
    """
    statement = re.split(r"\s+—\s+", kf, maxsplit=1)[0].lower()
    if _KF_CONSISTENT_MANIP_RE.search(statement):
        return True
    if _KF_NEGATED_RE.search(statement):
        return False
    return bool(_KF_MANIP_RE.search(statement))


def _uncalibrated_contributors(agent_ids) -> list[str]:
    """Agents among `agent_ids` whose calibration model is UNCALIBRATED.

    Fails closed: an unreadable model is treated as UNCALIBRATED so the
    disclosure is always shown when status cannot be confirmed.
    """
    out: list[str] = []
    layer = get_calibration_layer()
    for aid in agent_ids:
        try:
            model = layer.load_model(aid)
            status = model.calibration_status
        except Exception:
            status = CalibrationStatus.UNCALIBRATED
        if status == CalibrationStatus.UNCALIBRATED:
            out.append(aid)
    return out


def _trained_contributors(agent_ids) -> list[tuple[str, str, str]]:
    """Agents among `agent_ids` whose calibration model is TRAINED, returned as
    (agent_id, benchmark_dataset, version) (plan 3.3).

    The dataset name/version are stored alongside the persisted model, so the
    report can cite the benchmark a calibrated confidence was measured against.
    Mirrors `_uncalibrated_contributors` but selects the TRAINED state.
    """
    out: list[tuple[str, str, str]] = []
    layer = get_calibration_layer()
    for aid in agent_ids:
        try:
            model = layer.load_model(aid)
        except Exception:
            continue
        if model.calibration_status == CalibrationStatus.TRAINED:
            out.append((aid, str(model.benchmark_dataset or "labelled benchmark"), str(model.version or "")))
    return out


def _verbatim_court_statement(agent_id: str, raw_score: float) -> str:
    """The court-inadmissibility statement VERBATIM, produced by the same
    core.calibration function that defines it (CalibrationLayer.calibrate).

    Never paraphrased here — if the wording in calibration.py changes, the
    report follows automatically.
    """
    try:
        return get_calibration_layer().calibrate(
            agent_id, raw_score, "final_verdict_confidence"
        ).court_statement
    except Exception as exc:
        logger.warning("Could not produce verbatim calibration court statement", error=str(exc))
        return ""

# A tool slug is lowercase tokens joined by underscores (e.g. "frequency_domain_
# analysis"). Friendly labels ("Frequency Domain Analysis") and pure narrative
# findings contain spaces / no attribution and are never matched by this.
_TOOL_SLUG_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)+$")
_KF_PCT_RE = re.compile(r"\s*\(\d+(?:\.\d+)?%\)\s*$")


def _cited_tool_slug(kf: str) -> str | None:
    """Return the tool slug a `finding — tool (NN%)` key finding attributes itself
    to, lowercased, or None when it cites no specific tool."""
    if "—" not in kf:
        return None
    tail = _KF_PCT_RE.sub("", kf.rsplit("—", 1)[-1]).strip().lower()
    return tail or None

def build_deterministic_report(
    case_data: dict[str, Any],
    visual_context: Any | None,
    agent_syntheses: dict[str, Any],  # maps Agent ID to AgentSynthesisOutput
    arbiter_deliberation: ArbiterDeliberationResult,
    tool_coverage: dict[str, Any],
    execution_metadata: dict[str, Any],
    groq_used: bool = False,
    display_verdict: str | None = None,
    capability_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generates all final report sections deterministically from actual investigation data and deliberation results.

    `display_verdict` is the mapped, user-facing verdict (AUTHENTIC / SUSPICIOUS /
    MANIPULATED / INCONCLUSIVE). When provided it is used for the narrative labels
    so the report prose matches ForensicReport.overall_verdict exactly — they are
    no longer derived from two different strings.

    `capability_manifest` is the per-investigation tool manifest (plan 0.6). When
    not passed explicitly it is taken from the task-local handoff set by
    core.capability_manifest.build_capability_manifest, falling back to a
    coverage-only manifest so the report never ships without one.
    """

    # Extract file/case facts
    filename = str(case_data.get("filename") or "evidence_file")
    sha256 = str(case_data.get("sha256") or "unknown_hash")
    mime_type = str(case_data.get("mime_type") or "image/unknown")
    file_size_bytes = case_data.get("file_size_bytes") or 0
    file_size_kb = round(file_size_bytes / 1024, 2)

    # Normalise syntheses to Dict of AgentSynthesisOutput
    norm_syn: dict[str, AgentSynthesisOutput] = {}
    for aid, val in agent_syntheses.items():
        if isinstance(val, dict):
            norm_syn[aid] = AgentSynthesisOutput(**val)
        else:
            norm_syn[aid] = val

    # Helper: read visual context fields safely
    vis_available = False
    vis_desc = ""
    vis_source = "none"
    vis_ext_llm = False

    if visual_context:
        vis_available = True
        vis_desc = (
            getattr(visual_context, "scene_description", None)
            or getattr(visual_context, "content_description", "")
        )
        vis_source = getattr(visual_context, "source", "none")
        vis_ext_llm = getattr(visual_context, "external_llm_used", False)
    vis_cached = bool(getattr(visual_context, "cached", False)) if visual_context else False

    # ── Capability manifest (plan 0.6) — resolve once, used by Methodology,
    # Limitations, Reproducibility, and truthful tool naming below.
    manifest = (
        capability_manifest
        or get_current_manifest()
        or build_manifest_from_coverage(tool_coverage)
    )
    _manifest_tools: list[dict[str, Any]] = list(manifest.get("tools") or [])
    _research_on = bool(manifest.get("research_models_enabled"))
    _tool_status: dict[str, str] = {
        str(t.get("tool")): str(t.get("execution_status") or t.get("status") or "ran")
        for t in _manifest_tools
    }

    def _display_tool(tool: str) -> str:
        """Tool name for report prose, annotated with the actual method when the
        name implies a neural examination that did not run (plan 0.10)."""
        return truthful_tool_display(
            str(tool),
            research_models_enabled=_research_on,
            status=_tool_status.get(str(tool), "ran"),
        )

    # ── Calibration status (plan 0.7) — resolved before any confidence is rendered.
    _uncal_agents = _uncalibrated_contributors(norm_syn.keys())
    _trained_agents = _trained_contributors(norm_syn.keys())
    uncalibrated = is_system_uncalibrated() or bool(_uncal_agents)

    # ── Coverage figures (plan 3.8) — needed by the executive summary's first
    # sentence, so computed before the narrative.
    _cov_completed = len(tool_coverage.get("completed_tools", []) or [])
    _cov_failed = len(tool_coverage.get("failed_tools", []) or [])
    _cov_denominator = _cov_completed + _cov_failed
    coverage_pct = round(100.0 * _cov_completed / _cov_denominator, 1) if _cov_denominator else 100.0
    _critical_failures = [
        str(x) for x in (getattr(arbiter_deliberation, "tool_failures_affecting_report", None) or [])
    ]

    # --- 1. Executive Summary ---
    # Prefer the mapped/user-facing verdict so narrative prose == overall_verdict.
    verdict_label = (
        display_verdict.replace("_", " ").title()
        if display_verdict
        else arbiter_deliberation.final_verdict.replace("_", " ").title()
    )
    # Round half-up to match the frontend header's JS Math.round (toPct). Python's
    # built-in round() is banker's rounding (half-to-even), which at an exact .5
    # boundary (e.g. 0.925 → 92) disagrees with the header (→ 93), surfacing two
    # different confidence numbers for the same verdict.
    confidence_pct = int(arbiter_deliberation.final_confidence * 100 + 0.5)

    agent_list = [f"Agent {aid[-1]}" for aid in norm_syn.keys()]
    n_agents = len(agent_list)

    # Sentence 0 — verdict qualification (plan 3.8): when coverage is materially
    # limited or a critical tool failed, the FIRST sentence of the executive
    # summary states the limitation before any verdict is mentioned.
    _s0 = ""
    if coverage_pct < 70.0 or _critical_failures:
        _qual_bits = []
        if coverage_pct < 70.0:
            _qual_bits.append(
                f"tool coverage was limited to {coverage_pct:.0f}% of applicable tools "
                f"({_cov_failed} of {_cov_denominator} did not complete)"
            )
        if _critical_failures:
            _qual_bits.append(
                "critical check(s) could not be verified: "
                + "; ".join(_critical_failures[:3])
            )
        _s0 = (
            "Analysis limitation: " + " and ".join(_qual_bits) +
            " — the verdict below is qualified by this limitation."
        )

    # Sentence 1 — core verdict statement
    _article = "an" if verdict_label[:1].upper() in "AEIOU" else "a"
    _conf_phrase = (
        f"**{confidence_pct}%** indicative (uncalibrated) confidence"
        if uncalibrated
        else f"**{confidence_pct}%** confidence"
    )
    _s1 = (
        f"Forensic examination of `{filename}` ({mime_type}) returned {_article} "
        f"**{verdict_label}** verdict with {_conf_phrase} "
        f"after {n_agents} specialist agent{'' if n_agents == 1 else 's'} completed analysis."
    )

    # Sentence 2 — evidence basis (strongest finding or agent synthesis)
    _pos_findings = [
        f for f in (arbiter_deliberation.strongest_findings or [])
        if getattr(f, "evidence_verdict", None) == "POSITIVE"
    ]
    _verdicts_upper = (display_verdict or "").upper()
    if _pos_findings:
        _top = _pos_findings[0]
        _stmt = getattr(_top, "finding_statement", None) or str(_top)
        _s2 = f"Convergent signals — including {_stmt} — formed the primary evidentiary basis for this determination."
    elif _verdicts_upper in ("MANIPULATED", "SUSPICIOUS"):
        _s2 = (
            "Forensic signals identified by active agents contained statistically significant "
            "anomalies inconsistent with an authentic, unmodified file."
        )
    elif _verdicts_upper == "AUTHENTIC":
        _manip_pct = int(round(arbiter_deliberation.final_confidence * 100))
        # Modality-aware domain phrasing — "pixel integrity / statistical frequency"
        # is meaningless on an audio/video/document file (it read as an image-template
        # leak on the audio report).
        _mt = (mime_type or "").lower()
        if _mt.startswith("audio/"):
            _domains = "acoustic, voice-biometric, and provenance"
        elif _mt.startswith("video/"):
            _domains = "visual, audio-track, and temporal-integrity"
        elif _mt == "application/pdf" or _mt.startswith("text/") or "document" in _mt:
            # P0.2 — only claim "textual" coverage when document CONTENT was
            # actually analyzed (native LLM doc read). The metadata-only path
            # (Agent5 structure/provenance tools) never inspects rendered text, so
            # claiming textual checks there is an overstatement.
            _domains = "textual, structural, and provenance" if vis_ext_llm else "metadata and file-structure"
        elif _mt.startswith("image/"):
            _domains = "pixel integrity, statistical frequency, and provenance"
        else:
            _domains = "integrity, statistical, and provenance"
        # Plan 3.5 — neutral wording only: state what the executed checks found,
        # never the canned "consistent with an unmodified original" claim.
        _s2 = (
            f"Independent checks across {_domains} domains returned no manipulation indicators."
        )
        # Qualified-verdict coverage caveat: on the local-only (no holistic media
        # model) path the synthesis/AI determination is screening-tier, so a clean
        # audio/video/document result must NOT be presented as a full clearance.
        _is_doc = (
            _mt == "application/pdf" or _mt.startswith("text/") or "document" in _mt
        )
        if _mt.startswith(("audio/", "video/")) and not vis_ext_llm:
            _s2 += (
                " Note: holistic synthetic-speech / deepfake assessment is limited "
                "without a dedicated media model on this analysis path, so a clean "
                "result does not exclude high-quality AI synthesis."
            )
        elif _is_doc and not vis_ext_llm:
            _s2 += (
                " Note: this path examined container metadata and file structure only — "
                "no content-level or rendered-page forgery detection was performed, so a "
                "clean result does not exclude forged visible content or machine-authored text."
            )
    else:
        _s2 = (
            "Evidence across active analytical domains produced ambiguous or conflicting signals "
            "that preclude a definitive conclusion without additional context."
        )

    # Sentence 3 — coverage caveat, included ONLY when something did not fully
    # complete. A clean, fully-completed run needs no coverage sentence in the
    # executive summary: the methodology section and the reliability_note (rendered
    # directly under the summary) carry the tool inventory. Keeping the summary to
    # verdict + evidence basis (+ caveat when warranted) avoids the 5–6 sentence wall
    # of methodology meta that read as boilerplate.
    _n_failed = len(list(tool_coverage.get("failed_tools", []) or []))
    _n_degraded = len(list(tool_coverage.get("degraded_tools", []) or []))
    if _n_failed > 0:
        _s3 = (
            f"{_n_failed} forensic tool{'' if _n_failed == 1 else 's'} did not complete and "
            f"{'is' if _n_failed == 1 else 'are'} treated as a coverage limitation only, "
            f"not as evidence against the completed checks."
        )
    elif _n_degraded > 0:
        _s3 = (
            f"{_n_degraded} tool{'' if _n_degraded == 1 else 's'} ran in a reduced-fidelity "
            f"fallback and {'is' if _n_degraded == 1 else 'are'} treated as a coverage limitation."
        )
    else:
        _s3 = ""

    # Deterministic likelihood-ratio banding for the manipulation probability is
    # retained as its OWN report field (`likelihood_assessment`) for the full report
    # and exports. It is intentionally NOT appended to the executive summary: the
    # verdict and confidence already state the result, and the full likelihood-ratio
    # base-rate caveat read as legalese padding on the result page.
    manipulation_probability = _mirror_manipulation_probability(
        display_verdict or arbiter_deliberation.final_verdict,
        arbiter_deliberation.final_confidence,
    )
    likelihood_assessment = _likelihood_assessment(manipulation_probability)

    # Executive summary: limitation (if any) → verdict → evidence basis → coverage
    # caveat (if any). Visual-grounding provenance and methodology live in the
    # methodology section, never here.
    _summary_sentences = [s for s in (_s0, _s1, _s2, _s3) if s]
    exc_summary = " ".join(_summary_sentences)

    # --- 2. Evidence Overview ---
    route = execution_metadata.get("analysis_mode") or "hybrid"
    vis_source_label = "local ensemble" if vis_source == "local_ensemble" else ("external LLM" if vis_ext_llm else "none")

    overview_text = (
        f"File Specifications:\n"
        f"- Filename: {filename}\n"
        f"- MIME Type: {mime_type}\n"
        f"- Size: {file_size_kb} KB ({file_size_bytes} bytes)\n"
        f"- SHA-256 Hash: {sha256}\n"
        f"- Analysis Routing Mode: {route}\n"
        f"- Visual Context Profiling: Assisted by {vis_source_label}\n"
        f"- Active Analytical Units: {', '.join(norm_syn.keys())}"
    )

    # --- 3. Methodology ---
    # Group completed tools by agent
    methodology_parts = []

    agent1_tools = [t for t in tool_coverage.get("completed_tools", []) if t in (
        "ela_full_image", "neural_ela", "frequency_domain_analysis", "diffusion_artifact_detector", "jpeg_ghost_detect", "copy_move_detect"
    )]
    agent3_tools = [t for t in tool_coverage.get("completed_tools", []) if t in (
        "object_detection", "vector_contraband_search", "screenshot_layout_forensics", "screenshot_scene_applicability"
    )]
    agent5_tools = [t for t in tool_coverage.get("completed_tools", []) if t in (
        "exif_extract", "timestamp_analysis", "gps_timezone_validate", "file_structure_analysis"
    )]

    if agent1_tools:
        methodology_parts.append(f"Agent 1 (Image Integrity) successfully completed: {', '.join(_display_tool(t) for t in agent1_tools)}.")
    if agent3_tools:
        methodology_parts.append(f"Agent 3 (Object/Scene) successfully completed: {', '.join(_display_tool(t) for t in agent3_tools)}.")
    if agent5_tools:
        methodology_parts.append(f"Agent 5 (Metadata/Provenance) successfully completed: {', '.join(_display_tool(t) for t in agent5_tools)}.")

    not_app = tool_coverage.get("not_applicable_tools", [])
    if not_app:
        methodology_parts.append(f"The following tools were marked NOT APPLICABLE and excluded from active grading: {', '.join(not_app)}.")

    methodology = " ".join(methodology_parts) if methodology_parts else "No tools completed execution."

    # Plan 3.1 — structured Methodology generated from the capability manifest:
    # what each tool measures, the method that ACTUALLY ran, model + version, and
    # the measured-error placeholders ("not yet measured" until Phase-1 fills them).
    def _measured(value: Any) -> Any:
        return value if value is not None else "not yet measured"

    methodology_detail: list[dict[str, Any]] = []
    for t in _manifest_tools:
        _metrics = t.get("metrics") or {}
        methodology_detail.append({
            "tool": t.get("tool"),
            "display_name": _display_tool(str(t.get("tool"))),
            "measures": t.get("description") or "Forensic measurement (no per-tool description registered yet).",
            "actual_method": t.get("actual_method") or t.get("model") or t.get("method"),
            "model": t.get("model_name") or t.get("model") or None,
            "model_version": t.get("model_version") or "unrecorded",
            "license": t.get("license") or "",
            "status": t.get("execution_status") or t.get("status"),
            "tpr": _measured(_metrics.get("tpr")),
            "fpr": _measured(_metrics.get("fpr")),
            "threshold": _measured(_metrics.get("threshold")),
            "validation_dataset": _measured(_metrics.get("validation_dataset")),
        })

    # --- 4. Agent Deliberation Summary ---
    delib_parts = []
    for aid, syn in norm_syn.items():
        # Plan 0.7 — every confidence rendered for an UNCALIBRATED agent is
        # labelled indicative, never presented as a calibrated probability.
        _agent_conf_pct = int(float(syn.confidence_score or 0.0) * 100 + 0.5)
        _agent_conf_label = (
            f"{_agent_conf_pct}% indicative (uncalibrated) confidence"
            if aid in _uncal_agents
            else f"{_agent_conf_pct}% confidence"
        )
        delib_parts.append(
            f"{aid} concluded that the status was {syn.agent_verdict} "
            f"at {_agent_conf_label} (brief: {syn.agent_brief})."
        )

    if arbiter_deliberation.cross_agent_conflicts:
        delib_parts.append(f"Conflicts were detected during analysis: {'; '.join(arbiter_deliberation.cross_agent_conflicts)}")
    else:
        delib_parts.append("All active agent units maintained consistent assessments with no material conflicts.")

    agent_deliberation_summary = " ".join(delib_parts)

    # --- 5. Key Findings ---
    key_findings = []
    # Collect key findings from agents first
    for syn in norm_syn.values():
        key_findings.extend(syn.key_findings)
    # Deduplicate key findings
    seen_kfs = set()
    deduped_kfs = []
    for kf in key_findings:
        norm = kf.lower().strip()
        if norm not in seen_kfs:
            seen_kfs.add(norm)
            deduped_kfs.append(kf)

    # Court-defensibility guardrail: a key finding that attributes itself to a
    # specific forensic TOOL must trace to a tool that actually ran for this
    # evidence. LLM/vision synthesis can hallucinate plausible-sounding tools that
    # never executed (e.g. "scene_geometry_analysis", "lighting_analysis" on a
    # screenshot where physical-scene checks are N/A) with invented confidences —
    # such fabricated findings must never reach a signed report. Only slug-form
    # citations not backed by a real tool are dropped; friendly-label findings and
    # pure statistical narratives are left untouched. Context-only plumbing tools
    # that did NOT run are dropped; context-only tools that DID run (e.g.
    # visual_evidence_profile) are valid findings from a real tool execution.
    _real_tools = {
        str(t).lower()
        for key in ("completed_tools", "failed_tools", "not_applicable_tools", "skipped_tools")
        for t in (tool_coverage.get(key) or [])
    }
    _grounded_kfs = []
    for kf in deduped_kfs:
        _slug = _cited_tool_slug(kf)
        if _slug and _TOOL_SLUG_RE.match(_slug) and _slug not in _real_tools:
            _alias = _fuzzy_tool_alias(_slug, _real_tools)
            if _alias:
                # Remap the cited slug to the real tool in the finding text
                kf = re.sub(re.escape(_slug), _alias, kf, count=1)
            else:
                logger.warning(
                    "Dropped ungrounded key finding (cited tool did not run)",
                    extra={"cited_tool": _slug, "finding": kf[:160]},
                )
                continue
        _grounded_kfs.append(kf)
    deduped_kfs = _grounded_kfs

    # Material-first ordering: the result page renders only the top ~6 key findings,
    # in the order given. Collecting them in agent order (Agent1 → Agent3 → Agent5)
    # could bury a confirmed manipulation signal from a later agent beneath clean
    # lines from an earlier one. Stable-partition so asserted manipulation signals
    # lead and clean lines follow — order within each tier is preserved, and nothing
    # is dropped (exports still receive the full list).
    _material_kfs = [kf for kf in deduped_kfs if _kf_asserts_manipulation(kf)]
    _clean_kfs = [kf for kf in deduped_kfs if not _kf_asserts_manipulation(kf)]
    deduped_kfs = _material_kfs + _clean_kfs

    if not deduped_kfs:
        deduped_kfs = ["No anomalous signatures or physical manipulation artifacts were identified."]

    # --- 6. Integrity Assessment ---
    integrity_parts = []
    a1_syn = norm_syn.get("Agent1")
    if a1_syn:
        integrity_parts.append(f"Agent 1 analysis: {a1_syn.agent_brief}")
    # Add any specific integrity findings
    pos_int = [f for f in (arbiter_deliberation.strongest_findings or []) if f.signal_category == "integrity" and f.evidence_verdict == "POSITIVE"]
    if pos_int:
        integrity_parts.append(f"Identified tampering indicators: {', '.join([f.finding_statement for f in pos_int])}.")
    else:
        integrity_parts.append("No active tampering pattern, compression anomaly, or generative artifact was confirmed.")

    integrity_assessment = " ".join(integrity_parts)

    # --- 7. Object/Scene Context ---
    object_parts = []
    a3_syn = norm_syn.get("Agent3")
    if a3_syn:
        object_parts.append(f"Agent 3 assessment: {a3_syn.agent_brief}")
    if vis_available and vis_desc:
        object_parts.append(f"Visual scene description: {vis_desc}")
    else:
        # Plan 3.5 — no canned consistency claim when no visual read exists.
        object_parts.append(
            "No visual scene description was available; the object/scene assessment "
            "is limited to the executed tool findings."
        )

    object_scene_context = " ".join(object_parts)

    # --- 8. Metadata and Provenance ---
    meta_parts = []
    a5_syn = norm_syn.get("Agent5")
    if a5_syn:
        meta_parts.append(f"Agent 5 metadata assessment: {a5_syn.agent_brief}")
    pos_prov = [f for f in (arbiter_deliberation.strongest_findings or []) if f.signal_category == "provenance" and f.evidence_verdict == "POSITIVE"]
    if pos_prov:
        meta_parts.append(f"Metadata anomalies detected: {', '.join([f.finding_statement for f in pos_prov])}.")
    else:
        meta_parts.append("Metadata structures and binary headers conform to default standards for this file type.")

    metadata_and_provenance = " ".join(meta_parts)

    # --- 9. Limitations (plan 3.6 — auto-generated from manifest + coverage +
    # deliberation + calibration + visual-context provenance) ---
    limitations = []
    # Failures of tools (truthfully named)
    for f in tool_coverage.get("failed_tools", []):
        limitations.append(f"Execution failure: Tool `{_display_tool(f)}` did not complete successfully.")
    # Critical checks the deliberation flagged as unverifiable
    for cf in _critical_failures:
        _line = f"Unverified critical check: {cf}"
        if _line not in limitations:
            limitations.append(_line)
    # Gated-off research models (heuristic fallbacks ran under the neural name)
    _gated_tools = sorted(t["tool"] for t in _manifest_tools if (t.get("execution_status") or t.get("status")) == "gated_off")
    if _gated_tools:
        limitations.append(
            "Gated-off models: research neural models were disabled for "
            f"{', '.join(_gated_tools)}; classical fallback methods ran instead of the named neural models."
        )
    # Models unavailable at runtime
    _unavail_tools = sorted(t["tool"] for t in _manifest_tools if (t.get("execution_status") or t.get("status")) == "model_unavailable")
    if _unavail_tools:
        limitations.append(
            f"Model unavailable at runtime: {', '.join(_unavail_tools)} — treated as a coverage gap, not a clean result."
        )
    # Coverage percentage
    if _cov_denominator:
        limitations.append(
            f"Tool coverage: {coverage_pct:.0f}% of applicable tools completed "
            f"({_cov_completed} of {_cov_denominator})."
        )
    # Uncalibrated contributors
    if _uncal_agents:
        limitations.append(
            "Uncalibrated contributors: "
            f"{', '.join(_uncal_agents)} ran on UNCALIBRATED engineering-default confidence "
            "scaling; their confidence values are indicative only (see Reliability Notes)."
        )
    # Per-format exclusions (routing skipped these tools for this MIME type)
    _excluded = sorted(str(t) for t in (tool_coverage.get("not_applicable_tools") or []))
    if _excluded:
        limitations.append(
            f"Per-format exclusions for {mime_type}: {', '.join(_excluded)} were not applicable and did not run."
        )
    # Visual-context provenance
    if not vis_available:
        limitations.append("Visual grounding limitation: Shared visual context was unavailable.")
    elif vis_cached:
        _vc_created = str(getattr(visual_context, "created_at", "") or "").strip()
        limitations.append(
            "Visual-context provenance: the visual read was reused from a cached analysis of an "
            f"identical file (source: {vis_source}"
            + (f", originally created {_vc_created}" if _vc_created else ", original creation time unrecorded")
            + "), not recomputed this run."
        )

    if not limitations:
        limitations = ["No material tool coverage limitation was identified for the completed analysis path."]

    # --- 10. Reliability Notes ---
    reliability_notes = []
    # P0.1 / plan 0.7 — calibration disclosure. While any contributing detector
    # runs on UNCALIBRATED engineering-default scaling, every confidence number in
    # this report is indicative only and not a court-admissible calibrated
    # probability. This must be the most prominent reliability note, so it is
    # added first. (`uncalibrated` and `_uncal_agents` are resolved above, before
    # any confidence value is rendered.)
    if uncalibrated:
        from core.forensic_policy import ForensicPolicy
        _weights_clause = (
            " The relative reliability weights used to combine detector signals are likewise "
            "unsourced engineering defaults, not benchmarked reliabilities."
            if not getattr(ForensicPolicy, "WEIGHTS_ARE_VALIDATED", False)
            else ""
        )
        reliability_notes.append(
            "Reliability note (confidence calibration): The confidence scores in this report are "
            "INDICATIVE (UNCALIBRATED). They were produced by engineering-default scaling that was "
            "NOT fitted to any labelled forensic benchmark dataset, and MUST NOT be cited as "
            "calibrated probabilities in legal proceedings." + _weights_clause +
            " To obtain court-admissible scores, run site-specific calibration against a validated "
            "forensic benchmark."
        )
        # Plan 0.7 — the court-inadmissibility statement VERBATIM, produced by the
        # same core.calibration code path that defines it (never paraphrased here).
        _court_agent = _uncal_agents[0] if _uncal_agents else "Agent1"
        _court_stmt = _verbatim_court_statement(
            _court_agent, float(arbiter_deliberation.final_confidence)
        )
        if _court_stmt:
            reliability_notes.append("Calibration court statement (verbatim): " + _court_stmt)
        if _uncal_agents:
            reliability_notes.append(
                "Uncalibrated contributing agents: "
                + ", ".join(_uncal_agents)
                + ". Every confidence value rendered for these agents in this report is "
                "labelled 'indicative (uncalibrated)'."
            )
    # Plan 3.3 — positive calibration disclosure for agents whose detector scores
    # were fitted to a labelled forensic benchmark (CalibrationStatus.TRAINED).
    # Cites the dataset name and the persisted model version so a calibrated
    # confidence can be traced to the benchmark it was measured against.
    if _trained_agents:
        _cites = "; ".join(
            f"{aid} — calibrated on {ds}" + (f" (model {ver})" if ver else "")
            for aid, ds, ver in _trained_agents
        )
        reliability_notes.append(
            "Calibration disclosure (trained): confidence scores for the following "
            "contributing agent(s) were fitted to a labelled forensic benchmark and "
            "carry measured reliability rather than engineering defaults — " + _cites + "."
        )
    if groq_used:
        reliability_notes.append(
            "Narrative wording was assisted by an external text model; the verdict, confidence, "
            "and findings were computed by the arbiter from tool outputs."
        )
    else:
        reliability_notes.append(
            "The report narrative was generated deterministically from tool findings; no external text model was used."
        )

    if vis_available:
        if vis_ext_llm:
            reliability_notes.append("Visual reliability context was assisted by an external LLM and cross-checked against local forensic tools.")
        else:
            reliability_notes.append("Visual reliability context was generated using local forensic models and deterministic image-processing tools.")
        # II.3-3 — disclose provenance when the visual read was reused from the
        # cross-session content-hash cache rather than produced fresh this run.
        if vis_cached:
            reliability_notes.append(
                "Provenance: the visual-context read was reused from a cached analysis of an "
                "identical file (same content hash) from an earlier session, not recomputed this run."
            )
    else:
        reliability_notes.append("No visual context was used to ground the report.")

    # --- 11. Final Conclusion ---
    _conf_label = f"{confidence_pct}% indicative (uncalibrated) confidence" if uncalibrated else f"{confidence_pct}% confidence"
    final_conclusion = (
        f"`{filename}` is assessed **{verdict_label}** at {_conf_label}, on the weight of the completed checks."
    )

    # --- 12. Reproducibility block (plan 3.7) ---
    # Per-section reproducibility tags: this builder is fully deterministic; the
    # downstream Groq refiner only rewrites _LLM_REFINABLE_SECTIONS, and when it
    # does, `groq_used`/its own reliability note discloses it. prompt_version /
    # temperature are recorded only where they already exist in the inputs.
    reproducibility = {
        "model_versions": {
            str(t.get("tool")): (t.get("model_version") or t.get("model_name") or t.get("model") or None)
            for t in _manifest_tools
        },
        "prompt_version": execution_metadata.get("prompt_version"),
        "temperature": execution_metadata.get("temperature"),
        "sections": {
            sec: ("llm_assisted" if groq_used and sec in _LLM_REFINABLE_SECTIONS else "deterministic")
            for sec in _REPORT_SECTIONS
        },
        "narrative_mode": "llm_assisted" if groq_used else "deterministic",
        "coverage_percent": coverage_pct,
    }

    return {
        "case_id": case_data.get("case_id"),
        "session_id": case_data.get("session_id"),
        "evidence_overview": overview_text,
        "execution_metadata": execution_metadata,
        "visual_context_summary": vis_desc if vis_available else "none",

        "agent_syntheses": {k: (v.model_dump() if hasattr(v, "model_dump") else v) for k, v in agent_syntheses.items()},
        "arbiter_deliberation": arbiter_deliberation.model_dump(),

        "executive_summary": exc_summary,
        "methodology": methodology,
        "methodology_detail": methodology_detail,
        "agent_deliberation_summary": agent_deliberation_summary,
        "key_findings": deduped_kfs,
        "integrity_assessment": integrity_assessment,
        "object_scene_context": object_scene_context,
        "metadata_and_provenance": metadata_and_provenance,
        "limitations": limitations,
        "reliability_notes": reliability_notes,
        "likelihood_assessment": likelihood_assessment,
        "manipulation_probability": manipulation_probability,
        "capability_manifest": manifest,
        "reproducibility": reproducibility,
        "final_conclusion": final_conclusion,

        "final_verdict": arbiter_deliberation.final_verdict,
        "confidence_score": arbiter_deliberation.final_confidence,
        "confidence_reason": arbiter_deliberation.confidence_reason
    }
