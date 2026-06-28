from __future__ import annotations

import asyncio
import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from core.agent_personas import get_agent_narrative_persona
from core.config import Settings
from core.finding_formatter import TOOL_LABELS
from core.finding_humanizer import CONTEXT_ONLY_TOOLS
from core.llm_client import LLMClient
from core.structured_logging import get_logger
from core.visual_context_models import VisualContext

logger = get_logger(__name__)

# ── Pydantic models for per-agent synthesis ──

class VisualContextSplit(BaseModel):
    agent1_image_integrity: dict = Field(default_factory=dict)
    agent3_object_scene: dict = Field(default_factory=dict)
    agent5_metadata_visual: dict = Field(default_factory=dict)
    source: Literal["llm_assisted", "local_ensemble", "none"] = "none"
    external_llm_used: bool = False
    available: bool = False
    limitations: list[str] = Field(default_factory=list)


class AgentSynthesisInput(BaseModel):
    agent_id: Literal["Agent1", "Agent2", "Agent3", "Agent4", "Agent5"]
    persona_name: str
    persona_rules: dict = Field(default_factory=dict)
    visual_context_section: dict | None = None
    visual_context_available: bool = False
    evidence_identity: str = ""
    completed_tools: list[str] = Field(default_factory=list)
    failed_tools: list[str] = Field(default_factory=list)
    not_applicable_tools: list[str] = Field(default_factory=list)
    findings: list[dict] = Field(default_factory=list)
    grounded_findings: list[dict] = Field(default_factory=list)
    agent_verdict: str = "INCONCLUSIVE"
    agent_confidence: float = 0.0
    confidence_reason: str = ""
    # Deep-analysis comparison fields — populated only when is_deep_analysis=True
    is_deep_analysis: bool = False
    phase1_verdict: str = ""
    phase1_confidence: float = 0.0


class AgentSynthesisOutput(BaseModel):
    agent_id: str
    agent_brief: str
    visual_context_summary: str = ""
    key_findings: list[str] = Field(default_factory=list)
    agent_verdict: str
    confidence_score: float
    confidence_reason: str = ""
    limitations: list[str] = Field(default_factory=list)
    phase_comparison: str = ""
    synthesis_source: Literal[
        "groq_refined",
        "deterministic_with_visual_context",
        "deterministic_tool_only",
        "groq_tool_only",
        # Per-investigation token budget rejected the LLM call (refiner reserve
        # protected) — the deterministic template was used instead.
        "deterministic_template",
    ]


# ── Helper functions ──

def split_visual_context(session_id: str, context_obj: VisualContext | None) -> VisualContextSplit:
    """Split the visual context into per-agent views."""
    if context_obj is None:
        return VisualContextSplit(
            agent1_image_integrity={},
            agent3_object_scene={},
            agent5_metadata_visual={},
            source="none",
            external_llm_used=False,
            available=False,
            limitations=["Visual context not available."]
        )

    # Image integrity
    img_integrity = (
        context_obj.image_integrity_context.model_dump()
        if hasattr(context_obj.image_integrity_context, "model_dump")
        else dict(context_obj.image_integrity_context or {})
    )
    # Carry the top-level identity/verdict fields onto Agent 1's axis so its brief
    # can render the complete integrity picture (file type, holistic verdict, what
    # the evidence is) without reaching outside its section.
    img_integrity.update({
        "file_type_assessment": context_obj.file_type_assessment or "",
        "authenticity_verdict": context_obj.authenticity_verdict or "",
        "scene_description": context_obj.scene_description or "",
    })

    # Object scene
    obj_scene = (
        context_obj.object_scene_context.model_dump()
        if hasattr(context_obj.object_scene_context, "model_dump")
        else dict(context_obj.object_scene_context or {})
    )
    obj_scene.update({
        "extracted_text": context_obj.extracted_text or [],
        "detected_objects": [
            (obj.model_dump() if hasattr(obj, "model_dump") else dict(obj or {}))
            for obj in (context_obj.detected_objects or [])
        ],
        "interface_elements": context_obj.interface_elements or [],
        "scene_description": context_obj.scene_description or "",
    })

    # Metadata visual
    meta_visual = (
        context_obj.metadata_visual_context.model_dump()
        if hasattr(context_obj.metadata_visual_context, "model_dump")
        else dict(context_obj.metadata_visual_context or {})
    )
    meta_visual.update({
        "visible_timestamps": context_obj.visible_timestamps or [],
        "file_type_assessment": context_obj.file_type_assessment or "",
    })

    return VisualContextSplit(
        agent1_image_integrity=img_integrity,
        agent3_object_scene=obj_scene,
        agent5_metadata_visual=meta_visual,
        source=context_obj.source,
        external_llm_used=context_obj.external_llm_used,
        available=True,
        limitations=context_obj.limitations or []
    )


def format_finding_first(finding: dict) -> str:
    """Format any finding dict to enforce the `[Finding] — [Tool(s)] ([Confidence]%)` syntax."""
    meta = finding.get("metadata") or {}
    tool_id = meta.get("tool_name") or finding.get("finding_type") or "forensic_tool"
    tool_label = TOOL_LABELS.get(tool_id, tool_id.replace("_", " ").title())

    verdict = str(finding.get("evidence_verdict") or "INCONCLUSIVE").upper()
    status = str(finding.get("status") or "").upper()

    # Honest default when a tool carries no narratable text: a failed/incomplete
    # tool is a coverage gap, never a fabricated "anomaly signature" line.
    if verdict == "ERROR" or status in ("INCOMPLETE", "TIMEOUT", "FAILED"):
        _default_text = f"{tool_label} did not complete — coverage gap"
    elif verdict in ("NEGATIVE", "CLEAN"):
        _default_text = "No supported anomaly signal"
    else:
        _default_text = "No determinate signal"

    # Extract finding text/signal
    finding_text = (
        meta.get("key_signal")
        or finding.get("reasoning_summary")
        or meta.get("summary")
        or finding.get("finding_type")
        or _default_text
    )

    finding_text = str(finding_text).strip()
    # Strip leaked internal grounding/annotation markers ("[UNCORROBORATED VISUAL
    # CLAIM]", "[WARNING]", …) prepended upstream by the grounding pass. The
    # grounding effect is already applied to verdict/confidence; the bracketed tag
    # must never reach a signed, court-facing key finding. Mirrors the per-agent
    # card path's strip in findings_humanizer so both surfaces agree.
    finding_text = re.sub(r"\[[A-Z][A-Z /_-]{3,}\]\s*", "", finding_text).strip()
    # Strip tool prefix if it duplicates the tool name
    if tool_label.lower() in finding_text.lower():
        for prefix in (tool_label + ":", tool_label + " -", tool_label + " —", tool_label):
            if finding_text.lower().startswith(prefix.lower()):
                finding_text = finding_text[len(prefix):].strip()
                break

    conf = finding.get("confidence_raw") or meta.get("confidence") or finding.get("raw_confidence_score")

    if verdict in ("NOT_APPLICABLE", "ERROR") or conf is None:
        return f"{finding_text} — {tool_label}"
    else:
        conf_pct = int(round(float(conf) * 100))
        return f"{finding_text} — {tool_label} ({conf_pct}%)"


# Modality-aware phrasing for the "holistic read flagged this" narrative so an
# audio/video/document agent never reads "holistic VISUAL assessment / see Visual
# Context" (there is no visual context for those). (assessment phrase, context ref).
_HOLISTIC_TERMS: dict[str, tuple[str, str]] = {
    "Agent1": ("holistic visual assessment", "Visual Context"),
    "Agent2": ("holistic audio analysis", "the audio analysis"),
    "Agent3": ("holistic scene assessment", "Visual Context"),
    "Agent4": ("holistic media analysis", "the media analysis"),
    "Agent5": ("holistic content analysis", "the content analysis"),
}


def _holistic_terms(agent_id: str) -> tuple[str, str]:
    return _HOLISTIC_TERMS.get(agent_id, ("holistic assessment", "the holistic read"))


_FILE_TYPE_ARTICLE = {
    "screenshot": "a screenshot",
    "photograph": "a photograph",
    "document_scan": "a scanned document",
    "ai_generated": "an AI-generated image",
    "synthetic": "a synthetic image",
    "composite": "a composite image",
    "digital_art": "a piece of digital art",
    "rendered": "a rendered image",
}


def compose_evidence_identity(visual_context: Any) -> str:
    """Compose a short 'what the evidence appears to be' fragment from the
    visual context, for use after 'The evidence presents as ...'.

    This is INFERENCE (vision-derived), not a forensic finding — the brief
    frames it as observed context, never as a conclusion.
    Returns "" when no usable context exists.
    """
    if visual_context is None:
        return ""
    ft = str(getattr(visual_context, "file_type_assessment", "") or "").strip().lower()
    scene = str(getattr(visual_context, "scene_description", "") or "").strip()

    lead = _FILE_TYPE_ARTICLE.get(ft, ft if ft and ft not in ("unknown", "") else "")
    if lead and scene:
        scene_frag = scene.rstrip(".")
        # Avoid "a screenshot depicting a screenshot of ..."
        if ft and ft in scene_frag.lower()[:20]:
            return scene_frag
        # The scene description from the vision model is frequently a full clause
        # ("A minimalist outdoor scene features a building...", "The image captures
        # a computer screen..."), not a noun phrase. Splicing it after "depicting a"
        # yields broken grammar ("depicting the image captures a computer screen").
        # Detect a finite verb or a sentence-style opener and, if present, attach
        # the scene as its own sentence instead.
        _scene_low = scene_frag.lower()
        _is_clause = bool(
            re.search(
                r"\b(is|are|was|were|be|features?|shows?|showing|depicts?|depicting|"
                r"captures?|capturing|contains?|containing|appears?|displays?|displaying|"
                r"includes?|including|presents?|reveals?|portrays?|illustrates?|"
                r"shows|has|have)\b",
                _scene_low,
            )
        ) or _scene_low.startswith(
            ("the image", "this image", "the photo", "this photo", "the screenshot",
             "the scene", "it ", "an image", "a view", "image of", "screenshot of", "photo of")
        )
        if _is_clause:
            return f"{lead}. {scene_frag[0].upper()}{scene_frag[1:]}"
        return f"{lead} depicting {scene_frag[0].lower()}{scene_frag[1:]}"
    if lead:
        return lead
    if scene:
        return scene.rstrip(".")
    return ""


_BOILERPLATE_FINDING_MARKERS = (
    "found no supported anomaly signal",
    "completed with no",
    "no anomaly",
    "returned an inconclusive result",
    "was bypassed",
    "completed and found no",
    "no manipulation indicators",
    "no significant findings",
)


def _is_boilerplate_finding(text: str) -> bool:
    t = (text or "").lower()
    return any(marker in t for marker in _BOILERPLATE_FINDING_MARKERS)


def _present_label(text: str) -> str:
    """Render an internal enum/label (e.g. 'ai_generated', 'ai_generated_suspect')
    as presentable prose, keeping the 'AI' acronym uppercase."""
    t = str(text or "").replace("_", " ").strip().lower()
    if not t:
        return t
    overrides = {
        "ai generated": "AI-generated",
        "ai generated suspect": "AI-generated (suspect)",
        "cannot determine": "indeterminate",
    }
    if t in overrides:
        return overrides[t]
    return " ".join("AI" if w == "ai" else w for w in t.split())


def _metadata_provenance_facts(findings: list[dict]) -> list[str]:
    """Surface concrete file/EXIF provenance facts as examiner-voice sentences.

    Agent 5's value is the provenance record itself — capture time, device,
    format, size, GPS — yet the anomaly-centric humanizer collapses a clean EXIF
    read to "an internally consistent metadata record" and drops every value.
    This pulls the real facts straight off the finding metadata so they headline
    Agent 5's Visual Context and key findings regardless of the anomaly verdict.
    """
    facts: list[str] = []
    seen: set[str] = set()

    def _add(text: str) -> None:
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            facts.append(text)

    for f in findings or []:
        meta = f.get("metadata") or {}
        tool = str(meta.get("tool_name") or f.get("finding_type") or "")
        if tool not in ("exif_extract", "file_hash_verify", "compression_risk_audit"):
            continue

        fmt = str(meta.get("mime_type") or "").strip()
        size = str(meta.get("file_size_human") or "").strip()
        if fmt or size:
            bits = [b for b in (fmt, size) if b]
            _add(f"File format and size: {', '.join(bits)}.")

        dt = str(
            meta.get("datetime_original")
            or meta.get("DateTimeOriginal")
            or meta.get("CreationDate")
            or ""
        ).strip()
        if dt:
            _add(f"Embedded capture timestamp: {dt}.")

        make = str(meta.get("camera_make") or meta.get("make") or meta.get("Make") or "").strip()
        model = str(meta.get("camera_model") or meta.get("model") or meta.get("Model") or "").strip()
        device = " ".join(p for p in (make, model) if p).strip()
        if device:
            _add(f"Capture device recorded in metadata: {device}.")

        total = meta.get("total_fields_extracted")
        if isinstance(total, (int, float)) and not isinstance(total, bool):
            n = int(total)
            _add(
                f"{n} metadata field(s) extracted."
                if n
                else "No embedded EXIF metadata fields were present."
            )

        if meta.get("gps_location") or meta.get("gps_coordinates") or meta.get("GPSLatitude"):
            _add("GPS coordinates are embedded in the metadata.")

    return facts


def generate_deterministic_agent_synthesis(input_data: AgentSynthesisInput) -> AgentSynthesisOutput:
    """Generates structured agent findings and summary deterministically based on tool results."""
    # Build key findings — surface real signals, but collapse clean results into
    # one coverage statement rather than emitting a generic boilerplate line per
    # clean tool (which floods the report with fallback-looking text).
    # Split findings by VERDICT, not by text heuristics. POSITIVE results are the
    # material signals that drive the verdict and must headline the key findings
    # and the brief. NEGATIVE/clean results are real (and now richly described) but
    # are subordinate under an alert verdict — listing them as "key findings" next
    # to a Manipulated verdict reads as a self-contradiction. They become the
    # headline only when the evidence itself is clean (no positives).
    _source_findings = input_data.grounded_findings or input_data.findings
    _positive: list[str] = []
    _clean: list[str] = []
    _clean_tools: list[str] = []
    for f in _source_findings:
        verdict = str(f.get("evidence_verdict") or "").upper()
        meta = f.get("metadata") or {}
        tool_id = str(meta.get("tool_name") or f.get("finding_type") or "")
        # Context/plumbing tools (shared visual profile reads, ROI/frame
        # extraction) are inputs to other checks, not independent forensic
        # signals — they must never surface as a "Key Finding".
        if tool_id in CONTEXT_ONLY_TOOLS:
            continue
        if verdict in ("NOT_APPLICABLE", "ERROR"):
            continue
        formatted = format_finding_first(f)
        tool_label = TOOL_LABELS.get(tool_id, tool_id.replace("_", " ").title())
        if verdict == "POSITIVE":
            _positive.append(formatted)
        else:  # NEGATIVE / INCONCLUSIVE — clean or ambiguous, not a manipulation signal
            _clean.append(formatted)
            if tool_label:
                _clean_tools.append(tool_label)

    _alert_verdict = str(input_data.agent_verdict or "").upper() in (
        "SUSPICIOUS", "MANIPULATED", "TAMPERED", "LIKELY_MANIPULATED",
    )
    if _positive:
        # Alert path: lead with the confirmed signals; fold the clean checks into
        # one trailing coverage line so they don't masquerade as key findings.
        key_findings = list(_positive)
        if _clean:
            _nc = len(_clean)
            key_findings.append(
                f"The remaining {_nc} completed check{'s' if _nc != 1 else ''} returned clean "
                f"results with no manipulation signal."
            )
    elif _alert_verdict:
        # Alert verdict driven by the holistic read, not a discrete tool POSITIVE.
        # Lead with the holistic signal so the key findings do not read as all-clean
        # beside a SUSPICIOUS/MANIPULATED verdict. Modality-aware wording.
        _assess, _ctx = _holistic_terms(input_data.agent_id)
        key_findings = [
            f"The {_assess} flagged this evidence as anomalous; see {_ctx} for the contributing read."
        ] + _clean[:10]
    elif _clean:
        # Clean path: the evidence is benign — surface the substantive clean
        # findings themselves (now richly described) so the section is informative
        # rather than a bare "nothing found" line.
        key_findings = _clean[:10]
    else:
        _n = len(set(_clean_tools))
        key_findings = [
            f"No manipulation indicators were found across {_n} forensic check{'s' if _n != 1 else ''}."
        ] if _n else []

    # ── Visual Context summary (the "Visual Context" field) ──────────────────
    # Lead with the observed evidence identity, then this agent's specific visual
    # axis (Agent1 integrity, Agent3 object/scene, Agent5 metadata). Always
    # non-empty so the Visual Context block renders for every agent — the identity
    # lead lives HERE, not in the agent_brief (which prevents the duplication).
    # The identity lead ("The evidence presents as ...") is Agent 3's domain only.
    # Agent 1 leads with its integrity axis and Agent 5 with provenance facts, so
    # the shared scene description never bleeds in as their visual context.
    identity_lead = ""
    if input_data.evidence_identity and input_data.agent_id == "Agent3":
        identity_lead = f"The evidence presents as {str(input_data.evidence_identity).rstrip('. ')}."

    # Agent 5: concrete file/EXIF provenance facts pulled straight off the tool
    # findings, so its Visual Context leads with real provenance instead of a bare
    # file-type lead (e.g. "a composite image") when the visual axis is sparse.
    meta_facts = (
        _metadata_provenance_facts(input_data.findings)
        if input_data.agent_id == "Agent5"
        else []
    )
    # Provenance facts strengthen Agent 5's key findings — they are the record
    # itself, not anomaly signals, so they surface even on a clean verdict. Lead
    # with them when there is no positive anomaly, otherwise append as support.
    if meta_facts:
        _existing_kf = "\n".join(key_findings).lower()
        _prov_lines = [
            f"{fact.rstrip('.')} — Metadata extraction"
            for fact in meta_facts
            if fact.rstrip(".").lower() not in _existing_kf
        ]
        if _prov_lines:
            key_findings = (key_findings + _prov_lines) if _positive else (_prov_lines + key_findings)

    # Render the agent's COMPLETE visual-context axis as refined prose — every
    # field from the shared visual context for this agent's dimension, nothing
    # trimmed or capped. Each non-empty field becomes one clean sentence.
    def _items(*keys: str) -> list[str]:
        for k in keys:
            raw = section.get(k)
            if raw:
                out = [
                    str(x.get("label") if isinstance(x, dict) else x).strip()
                    for x in raw
                ]
                out = [x for x in out if x]
                if out:
                    return out
        return []

    axis_sentences: list[str] = []
    section = input_data.visual_context_section or {}
    if input_data.visual_context_available and section:
        if input_data.agent_id == "Agent1":
            ftype = str(section.get("file_type_assessment") or "").strip()
            ass = str(section.get("integrity_assessment") or "").strip()
            verdict = str(section.get("authenticity_verdict") or "").strip()
            manip = _items("visible_manipulation_signals")
            aigen = _items("ai_generation_signals")
            edit = _items("editing_or_compositing_signals")
            comp = _items("compression_or_reupload_signals")
            regions = _items("regions_for_followup")
            # Whether the holistic visual read itself flags an issue. When it does
            # NOT, "manipulation indicators" like 'background removed' are benign
            # edits (e.g. a product cut-out), not deceptive manipulation — labelling
            # them as "manipulation indicators" beside an AUTHENTIC verdict is a
            # self-contradiction. Reframe them as observed editing in that case.
            _verdict_is_alert = verdict.upper() in (
                "AI_GENERATED", "MANIPULATED", "SUSPECT", "AI_GENERATED_SUSPECT", "LIKELY_MANIPULATED",
            ) or ass.lower() in ("likely_manipulated", "ai_generated_suspect")
            if ftype:
                axis_sentences.append(f"The visual model assessed the file type as {_present_label(ftype)}.")
            if ass and ass != "cannot_determine":
                axis_sentences.append(f"Its image-integrity assessment is '{_present_label(ass)}'.")
            if manip:
                if _verdict_is_alert:
                    axis_sentences.append(f"Visible manipulation indicators: {', '.join(manip)}.")
                else:
                    axis_sentences.append(
                        f"Observed editing consistent with benign processing rather than deceptive "
                        f"manipulation: {', '.join(manip)}."
                    )
            if aigen:
                axis_sentences.append(f"AI-generation indicators: {', '.join(aigen)}.")
            if edit:
                _edit_lbl = "Editing or compositing indicators" if _verdict_is_alert else "Observed editing or compositing"
                axis_sentences.append(f"{_edit_lbl}: {', '.join(edit)}.")
            if comp:
                axis_sentences.append(f"Compression or re-upload indicators: {', '.join(comp)}.")
            if regions:
                axis_sentences.append(f"Regions flagged for follow-up: {', '.join(regions)}.")
            if not (manip or aigen or edit or comp) and not _verdict_is_alert:
                axis_sentences.append("No visible manipulation, AI-generation, editing, or compression anomalies were observed.")
            elif not (manip or aigen or edit or comp) and _verdict_is_alert:
                axis_sentences.append(
                    "No single localized region was isolated, but the holistic visual read is anomalous (see below)."
                )
            if verdict and verdict != "CANNOT_DETERMINE":
                axis_sentences.append(f"Holistic visual authenticity read: {_present_label(verdict)}.")
        elif input_data.agent_id == "Agent3":
            desc = str(section.get("scene_description") or "").strip()
            objs = _items("objects", "detected_objects")
            people = _items("people")
            weapons = _items("weapons_or_dangerous_items")
            docs = _items("documents_or_ids")
            ui = _items("ui_elements", "interface_elements")
            text = _items("visible_text", "extracted_text")
            anomalies = _items("scene_inconsistencies")
            # Skip the scene restatement when the identity lead already carries it
            # (it is composed from the same scene description) to avoid the
            # "presents as <scene>. The scene shows <scene>." duplication.
            _ident = str(input_data.evidence_identity or "").lower()
            _desc_norm = desc.rstrip(".").lower()
            if desc and _desc_norm[:40] not in _ident:
                axis_sentences.append(f"The scene shows {desc.rstrip('.')}.")
            if objs:
                axis_sentences.append(f"Objects present: {', '.join(objs)}.")
            if people:
                axis_sentences.append(f"People observed: {', '.join(people)}.")
            if weapons:
                axis_sentences.append(f"Weapons or dangerous items: {', '.join(weapons)}.")
            if docs:
                axis_sentences.append(f"Documents or IDs: {', '.join(docs)}.")
            if ui:
                axis_sentences.append(f"UI elements: {', '.join(ui)}.")
            if text:
                axis_sentences.append(f"Visible text: {', '.join(text)}.")
            if anomalies:
                axis_sentences.append(f"Scene inconsistencies flagged: {', '.join(anomalies)}.")
            else:
                axis_sentences.append("No scene inconsistencies were flagged.")
        elif input_data.agent_id == "Agent5":
            # Lead with the concrete provenance facts from the file/EXIF tools, then
            # layer on any visible-in-image metadata clues. The file-type assessment
            # is intentionally NOT restated here — it is not provenance, and as a
            # bare lead it produced the "composite" leak.
            axis_sentences.extend(meta_facts)
            ts = _items("visible_timestamps")
            loc = _items("visible_location_clues")
            dev = _items("device_or_platform_clues")
            app = _items("software_or_app_clues")
            lws = _items("lighting_weather_season_clues")
            notes = _items("metadata_consistency_notes")
            contra = _items("metadata_contradictions")
            if ts:
                axis_sentences.append(f"Visible timestamps: {', '.join(ts)}.")
            if loc:
                axis_sentences.append(f"Location clues: {', '.join(loc)}.")
            if dev:
                axis_sentences.append(f"Device or platform clues: {', '.join(dev)}.")
            if app:
                axis_sentences.append(f"App or software clues: {', '.join(app)}.")
            if lws:
                axis_sentences.append(f"Lighting, weather, or season clues: {', '.join(lws)}.")
            if contra:
                axis_sentences.append(f"Provenance contradictions: {', '.join(contra)}.")
            if notes:
                axis_sentences.append(f"Metadata consistency notes: {', '.join(notes)}.")
            if not axis_sentences:
                axis_sentences.append(
                    "No embedded provenance metadata (timestamp, device, location, or format "
                    "record) was recovered from the file."
                )

    axis_detail = " ".join(axis_sentences).strip()

    _axis_fallback = {
        "Agent1": "no distinct image-integrity signals were observed",
        "Agent2": "no distinct acoustic or voice-integrity signals were observed",
        "Agent3": "no distinct object or scene context was observed",
        "Agent4": "no distinct temporal or media-integrity signals were observed",
        "Agent5": "no distinct metadata or provenance clues were observed",
    }.get(input_data.agent_id, "no distinct context was observed")

    if identity_lead and axis_detail:
        vis_summary = f"{identity_lead} {axis_detail}"
    elif identity_lead:
        vis_summary = f"{identity_lead} For this dimension, {_axis_fallback}."
    elif axis_detail:
        vis_summary = axis_detail
    else:
        vis_summary = f"For this dimension, {_axis_fallback}."

    # ── Agent Overview (the "agent_brief" field) — tools that ran + verdict ──
    # No visual identity here; the Visual Context field above carries that, so the
    # two blocks never duplicate each other.
    _axis_label = {
        "Agent1": "image-integrity",
        "Agent3": "scene and object",
        "Agent5": "metadata and provenance",
    }.get(input_data.agent_id, "forensic")
    # Count APPLICABLE checks only — a tool that returned NOT_APPLICABLE for this
    # evidence (e.g. a JPEG-compression tool on a lossless image, or a neural
    # fingerprint that does not apply) ran but performed no forensic check, so it
    # must not inflate "completed N check(s)". This keeps the result-page count
    # equal to the evidence-card's "N applicable forensic checks" (single source
    # of truth — previously the card said 3 while the report said 4).
    # Exclude context/plumbing tools AND chain-of-custody / file-type validation
    # tools — these are coverage/provenance inputs, not manipulation checks. This
    # MUST match the result-page agent header's "N checks" filter
    # (AgentFindingCard.tsx) so the brief's "completed N check(s)" never drifts
    # from the header count.
    _NON_FORENSIC_COUNT_TOOLS = {
        "file_hash_verify", "hash_verify", "custody_check", "file_type_validation",
    }
    _applicable_tools = set()
    for f in _source_findings:
        if str(f.get("evidence_verdict") or "").upper() == "NOT_APPLICABLE":
            continue
        if str(f.get("status") or "").upper() == "NOT_APPLICABLE":
            continue
        _t = str((f.get("metadata") or {}).get("tool_name") or f.get("finding_type") or "")
        if not _t or _t in CONTEXT_ONLY_TOOLS or _t in _NON_FORENSIC_COUNT_TOOLS:
            continue
        _applicable_tools.add(_t)
    _n_checks = len(_applicable_tools) or len(input_data.completed_tools) or len(_source_findings)
    # An alert verdict (_alert_verdict, computed above) can be driven by the
    # holistic visual read (e.g. an AI-generation determination) rather than a
    # discrete tool POSITIVE. In that case the brief must NOT claim "no
    # manipulation indicators" — that contradicts the verdict badge.
    # Verdict-appropriate wording: a signal is only "confirmed" for a MANIPULATED
    # verdict. For SUSPICIOUS/INCONCLUSIVE the signal is "flagged" — saying
    # "confirmed N manipulation signals supporting an inconclusive finding" reads
    # as a contradiction in terms.
    _vw = str(input_data.agent_verdict or "").replace("_", " ").lower().strip()
    _vu = str(input_data.agent_verdict or "").upper()
    _art = "an" if _vw[:1] in "aeiou" else "a"
    _is_manip_verdict = _vu in ("MANIPULATED", "TAMPERED", "LIKELY_MANIPULATED")
    _sig_verb = "confirmed" if _is_manip_verdict else "flagged"
    # "confirmed" pairs with a definite "manipulation signal"; "flagged" pairs with
    # a hedged "potential manipulation signal" — avoid "confirmed N potential ...".
    _sig_noun = "manipulation signal" if _is_manip_verdict else "potential manipulation signal"
    if _positive:
        findings_joined = "; ".join(_positive[:3])
        _n_sig = len(_positive)
        agent_brief = (
            f"The {_axis_label} examination completed {_n_checks} check(s) and {_sig_verb} "
            f"{_n_sig} {_sig_noun}(s). {findings_joined}."
        )
    elif _alert_verdict:
        _assess_b, _ctx_b = _holistic_terms(input_data.agent_id)
        agent_brief = (
            f"The {_axis_label} examination completed {_n_checks} check(s). No individual "
            f"tool isolated a discrete manipulation signal, but the {_assess_b} is "
            f"anomalous (see {_ctx_b} for the contributing read)."
        )
    elif _clean:
        # Lead with the strongest clean finding — the head of the overview should
        # not be a 3%-confidence line. Rank by the trailing "(NN%)" confidence and
        # de-prioritise any residual generic "no anomaly signal" phrasing.
        def _lead_rank(line: str) -> float:
            m = re.search(r"\((\d+)%\)\s*$", line.strip())
            conf = int(m.group(1)) if m else 0
            if "found no anomaly signal" in line.lower():
                conf -= 1000  # push generic phrasing to the back
            return conf
        _clean_lead = max(_clean, key=_lead_rank)
        agent_brief = (
            f"The {_axis_label} examination completed {_n_checks} check(s) and found no "
            f"supported manipulation indicators. {_clean_lead}"
        )
    else:
        agent_brief = (
            f"The {_axis_label} examination found no supported anomalies across the "
            f"applicable checks."
        )

    # Append the deterministic verdict so the overview states the outcome arrived.
    # No confidence % in the prose — the authoritative grounded confidence is shown
    # in the card header and per-agent metrics; citing a pre-grounding number here
    # drifts from it (e.g. brief "85%" beside a grounded 89% card header).
    if input_data.agent_verdict:
        _vv = str(input_data.agent_verdict).replace("_", " ").title()
        agent_brief += f" Verdict: {_vv}."

    # Derive the opinion / confidence reason from the SAME positive/clean split
    # that drives the brief, so the "Your Opinion" block can never state a
    # different signal count than the Agent Overview (e.g. brief "confirmed 6"
    # vs opinion "7 confirmed"). The verdict word stays consistent with the badge.
    _failed_note = (
        f" {len(input_data.failed_tools)} check(s) did not complete and are treated as coverage gaps."
        if input_data.failed_tools else ""
    )
    _n_pos = len(_positive)
    if _positive and _is_manip_verdict:
        confidence_reason = (
            f"{_n_pos} manipulation signal(s) were confirmed across {_n_checks} completed "
            f"check(s), supporting a manipulated finding.{_failed_note}"
        )
    elif _positive and "SUSPICIOUS" in _vu:
        confidence_reason = (
            f"{_n_pos} potential manipulation signal(s) were flagged across {_n_checks} "
            f"completed check(s); the evidence is suspicious pending corroboration.{_failed_note}"
        )
    elif _positive:
        confidence_reason = (
            f"{_n_pos} signal(s) were flagged across {_n_checks} completed check(s), but the "
            f"evidence remains inconclusive.{_failed_note}"
        )
    elif _alert_verdict:
        _assess_o, _ = _holistic_terms(input_data.agent_id)
        confidence_reason = (
            f"No discrete tool isolated a manipulation signal, but the {_assess_o} "
            f"supports {_art} {_vw or 'suspicious'} finding across "
            f"{_n_checks} completed check(s).{_failed_note}"
        )
    elif _clean:
        confidence_reason = (
            f"All {_n_checks} completed check(s) returned clean results with no manipulation "
            f"signal.{_failed_note}"
        )
    else:
        confidence_reason = (
            input_data.confidence_reason
            or f"{_n_checks} check(s) completed; the results were inconclusive.{_failed_note}"
        )

    source_mode = "deterministic_with_visual_context" if input_data.visual_context_available else "deterministic_tool_only"

    # Limitations are from failed tools
    limitations = []
    if input_data.failed_tools:
        limitations.append(f"Tool execution failures: {', '.join(input_data.failed_tools)}")

    return AgentSynthesisOutput(
        agent_id=input_data.agent_id,
        agent_brief=agent_brief,
        visual_context_summary=vis_summary,
        key_findings=key_findings,
        agent_verdict=input_data.agent_verdict,
        confidence_score=input_data.agent_confidence,
        confidence_reason=confidence_reason,
        limitations=limitations,
        synthesis_source=source_mode
    )


# Assertive manipulation language that must NOT appear when the deterministic
# verdict is clean/inconclusive (item 7 — verdict is the single source of truth).
_MANIPULATION_TERMS = (
    "manipulat", "tamper", "forged", "forgery", "fabricat", "doctored", "spliced",
    "splicing", "deepfake", "ai-generated", "ai generated", "synthetic", "falsified",
    "altered", "edited to deceive", "not authentic", "inauthentic",
)
_CLEAN_VERDICTS = {"AUTHENTIC", "NEGATIVE", "NOT_APPLICABLE", "CLEAN", ""}

# LLMs commonly hallucinate near-miss tool slugs. Map known hallucinated names
# to the real tool slugs so valid findings are not silently dropped.
_TOOL_ALIAS_MAP: dict[str, str] = {
    "timestamp_record": "timestamp_analysis",
    "timestamp_check": "timestamp_analysis",
    "timestamp_analyzer": "timestamp_analysis",
    "timestamp_correlation": "timestamp_analysis",
    "timestamp_validator": "timestamp_analysis",
    "device_make_model": "device_fingerprint_db",
    "exif_provenance_chain": "provenance_chain_verify",
    "exif_provenance_check": "provenance_chain_verify",
    "exif_provenance": "exif_extract",
    "exif_fingerprint": "exif_extract",
    "exif_field_count_check": "exif_extract",
    "exif_analyzer": "exif_extract",
    "exif_anomaly_check": "metadata_anomaly_score",
    "gps_coordinates": "gps_timezone_validate",
    "gps_coordinate_check": "gps_timezone_validate",
    "gps_presence": "gps_timezone_validate",
    "metadata_provenance": "metadata_anomaly_score",
    "c2pa_verify": "provenance_chain_verify",
    "c2pa_check": "provenance_chain_verify",
    "file_identity": "file_structure_analysis",
    "hash_check": "file_hash_verify",
    "scene_geometry": "scene_incongruence",
}


def _fuzzy_tool_alias(cited: str, agent_tools: set[str]) -> str | None:
    """Return the real tool slug if ``cited`` is a known LLM hallucination,
    or a close substring/overlap match against the agent's real tool set.
    Returns None when no reasonable alias is found."""
    # 1. Exact alias map
    if cited in _TOOL_ALIAS_MAP:
        alias = _TOOL_ALIAS_MAP[cited]
        if alias in agent_tools:
            return alias
    # 2. Substring overlap: check if the cited slug is a prefix/suffix of a
    #    real tool, or vice versa (min 6 chars to avoid false matches).
    if len(cited) >= 6:
        for real in agent_tools:
            if len(real) >= 6 and (cited in real or real in cited):
                return real
    return None


def _text_contradicts_verdict(text: str, verdict: str) -> bool:
    """True if narrative text asserts manipulation while the deterministic verdict
    is clean/inconclusive. Used to reject contradictory LLM narrative and keep the
    deterministic text, so findings never disagree with the verdict."""
    if not text:
        return False
    if str(verdict or "").upper() not in _CLEAN_VERDICTS:
        return False  # alert verdicts may legitimately use manipulation language
    low = text.lower()
    
    if not any(term in low for term in _MANIPULATION_TERMS):
        return False

    # Scrub common negations to avoid false positives (e.g. "no manipulated regions")
    negations = [
        r"no\s+[\w\s-]*?(?:" + "|".join(_MANIPULATION_TERMS) + r")",
        r"absence\s+of\s+[\w\s-]*?(?:" + "|".join(_MANIPULATION_TERMS) + r")",
        r"without\s+[\w\s-]*?(?:" + "|".join(_MANIPULATION_TERMS) + r")",
        r"zero\s+[\w\s-]*?(?:" + "|".join(_MANIPULATION_TERMS) + r")",
        r"0\s+[\w\s-]*?(?:" + "|".join(_MANIPULATION_TERMS) + r")",
        r"checked\s+for\s+[\w\s-]*?(?:" + "|".join(_MANIPULATION_TERMS) + r")",
        r"did\s+not\s+detect\s+[\w\s-]*?(?:" + "|".join(_MANIPULATION_TERMS) + r")",
        r"failed\s+to\s+find\s+[\w\s-]*?(?:" + "|".join(_MANIPULATION_TERMS) + r")",
        r"negative\s+for\s+[\w\s-]*?(?:" + "|".join(_MANIPULATION_TERMS) + r")",
        r"clear\s+of\s+[\w\s-]*?(?:" + "|".join(_MANIPULATION_TERMS) + r")",
        r"lack\s+of\s+[\w\s-]*?(?:" + "|".join(_MANIPULATION_TERMS) + r")",
        r"free\s+(?:from|of)\s+[\w\s-]*?(?:" + "|".join(_MANIPULATION_TERMS) + r")",
        r"does\s+not\s+appear\s+(?:" + "|".join(_MANIPULATION_TERMS) + r")",
    ]
    scrubbed = low
    for pat in negations:
        scrubbed = re.sub(pat, "", scrubbed)
        
    return any(term in scrubbed for term in _MANIPULATION_TERMS)


def _round_pcts(text: str) -> str:
    """Round any fractional percentage in narrative text to a whole number.

    A confidence/metric value formed as ``value * 100`` can carry float-precision
    noise (e.g. ``0.4 * 100 == 39.999999999999996``). If that leaks into prose it
    renders as ``39.999999999999996%`` — defensively normalise it to ``40%``."""
    if not text:
        return text
    return re.sub(r"(\d+)\.\d+\s*%", lambda m: f"{round(float(m.group(0).rstrip('% ')))}%", text)


_VERDICT_TIER = {
    "authentic": 0, "clean": 0, "genuine": 0, "unmodified": 0, "pristine": 0,
    "inconclusive": 1,
    "suspicious": 2,
    "manipulated": 3, "tampered": 3, "fabricated": 3, "fake": 3,
    "synthetic": 3, "deepfake": 3, "forged": 3,
}


def _verdict_tier(verdict: str) -> int | None:
    v = (verdict or "").lower()
    for word, tier in _VERDICT_TIER.items():
        if word in v:
            return tier
    return None


def _brief_misstates_verdict(text: str, verdict: str) -> bool:
    """True when an LLM brief states an assessment tier that disagrees with the
    deterministic verdict — e.g. brief 'assessed as suspicious' while the verdict
    is MANIPULATED. The grounded/arbiter verdict can elevate after the brief was
    drafted; an understated brief reads as a contradiction on the card."""
    actual = _verdict_tier(verdict)
    if actual is None:
        return False
    # Only capture an explicit verdict word in an assessment phrase, so
    # "evidence is assessed as suspicious" yields "suspicious" (not "assessed").
    m = re.search(
        r"(?:assessed as|evidence is|deemed|classified as|rated|appears)\s+"
        r"(?:likely\s+|an?\s+|to be\s+)?"
        r"(authentic|clean|genuine|unmodified|pristine|inconclusive|suspicious|"
        r"manipulated|tampered|fabricated|fake|synthetic|deepfake|forged)",
        (text or "").lower(),
    )
    if not m:
        return False
    claimed = _VERDICT_TIER.get(m.group(1))
    return claimed is not None and claimed != actual


def _is_echoed_instruction(text: str) -> bool:
    """True when an LLM brief parrots the prompt's field instructions instead of
    writing prose (seen under model degradation / overload). Such a brief reads as
    ``"1 check ran with decisive metrics: tool (40%); verdict: X, confidence: Y%"``
    — reject it and keep the deterministic brief."""
    low = (text or "").lower()
    return (
        "decisive metric" in low 
        or "verdict + confidence" in low 
        or "<" in low 
        or "write one sentence" in low 
        or "write two sentences" in low 
        or "write one clear sentence" in low
    )


# Bare file-type / identity labels the vision pass may echo. On their own these
# are not a visual-context summary — they carry none of the per-agent axis detail
# the deterministic builder already rendered.
_BARE_IDENTITY_VC = frozenset({
    "photograph", "photo", "picture", "image", "screenshot", "screen capture",
    "document", "document scan", "scanned document", "composite", "composite image",
    "digital art", "rendered image", "synthetic image", "ai-generated image", "unknown",
})


def _is_degenerate_visual_summary(text: str, baseline: str = "") -> bool:
    """True when a refined ``visual_context_summary`` carries less information than
    the deterministic axis prose and must not overwrite it.

    The LLM polish occasionally collapses an agent's visual axis to a bare
    file-type label ("Photograph.") or a sentence fragment. Accepting that silently
    replaces several sentences of real axis detail with a useless word.
    """
    t = (text or "").strip().rstrip(".").strip().lower()
    if not t:
        return True
    if t in _BARE_IDENTITY_VC:
        return True
    if len(t.split()) < 4:
        return True
    # A refined summary far shorter than substantive deterministic prose has dropped
    # the axis detail the deterministic builder already rendered.
    base = (baseline or "").strip()
    if len(base) >= 60 and len(text.strip()) < 0.15 * len(base) and len(text.strip()) < 50:
        return True
    return False


def _build_persona_system_prompt(agent_ids: list[str], is_deep: bool = False) -> str:
    """
    Build the Groq system prompt with per-agent expert voice instructions.
    The persona voice definitions are the single source of truth — they live
    in agent_personas.py and are injected here at call time so a change to
    a persona definition automatically propagates to the synthesis prompt.
    When is_deep=True, adds a 4th field (phase_comparison) to the output schema.
    """
    voice_blocks: list[str] = []
    for aid in agent_ids:
        persona = get_agent_narrative_persona(aid)
        if persona:
            vocab = ", ".join(persona.vocabulary_signature[:8])
            forbidden = ", ".join(f'"{p}"' for p in persona.forbidden_phrases[:5])
            voice_blocks.append(
                f"**{aid} — {persona.expert_name}, {persona.title}**\n"
                f"Voice: {persona.voice_style}\n"
                f"Emphasis: {persona.emphasis}\n"
                f"Finding lead: {persona.finding_lead}\n"
                f"Domain vocabulary to use naturally: {vocab}.\n"
                f"Never use these phrases: {forbidden}."
            )

    persona_section = "\n\n".join(voice_blocks)

    agent_hints = {
        "Agent1": "summarizing the integrity axis",
        "Agent2": "summarizing the audio/spectral context",
        "Agent3": "summarizing the scene and objects",
        "Agent4": "summarizing the temporal/video context",
        "Agent5": "summarizing the provenance record",
    }
    
    schema_parts = []
    for aid in agent_ids:
        hint = agent_hints.get(aid, "summarizing the forensic context")
        part = (
            f"  \"{aid}\": {{\n"
            f"    \"visual_context_summary\": \"Write one clear sentence {hint} here.\",\n"
            "    \"agent_brief\": \"Write two sentences of expert prose summarizing the checks and rationale here.\",\n"
            "    \"key_findings\": [\n"
            "      \"Metric-specific finding — tool_name (conf%)\",\n"
            "      ...\n"
            "    ]"
        )
        if is_deep:
            part += ",\n    \"phase_comparison\": \"Write one sentence phase comparison here.\""
        part += "\n  }"
        schema_parts.append(part)
        
    schema_json = "{\n" + ",\n".join(schema_parts) + "\n}"

    prompt = (
        "You are a forensic narrative specialist writing expert testimony for a multi-agent "
        "digital evidence analysis system. Each agent has a distinct expert identity. "
        "Write ONLY in their assigned voice — not in generic template language.\n\n"
        + persona_section
        + "\n\n"
        "━━━ INVIOLABLE CONSTRAINTS ━━━\n"
        "1. NEVER alter 'agent_verdict' or 'agent_confidence'. These are deterministic forensic "
        "measurements sealed before your call. Your job is to NARRATE, not to re-score.\n"
        "2. NEVER name any AI provider, model, or tool vendor "
        "(e.g. Gemini, CLIP, YOLO, Groq, Llama, Florence). Use forensic domain terms instead.\n"
        "3. Write in the present tense. Analysis is complete; report findings as established facts.\n"
        "4. Return ONLY valid JSON. No markdown fences, no commentary outside the JSON object.\n"
        "5. The verdict MUST be echoed consistently across all three fields. "
        "If agent_verdict is AUTHENTIC or INCONCLUSIVE: never imply manipulation, tampering, "
        "forgery, deepfake, or AI generation — describe outcomes as clean, within normal parameters, "
        "or inconclusive. If agent_verdict is SUSPICIOUS or MANIPULATED: never call the evidence "
        "authentic or unaltered.\n\n"
        "━━━ THREE FIELDS — RULES FOR EACH ━━━\n\n"
        "FIELD 1 — visual_context_summary\n"
        "Translate this agent's 'visual_context_section' into one precise, evidence-specific sentence.\n"
        "Write from the agent's own forensic axis — do NOT describe what another agent covers:\n"
        "  • Agent1 axis (image integrity): State the holistic authenticity read of the image — "
        "file type as a forensic attribute (e.g. 'JPEG photograph', 'PNG screenshot', "
        "'AI-diffusion composite'), any AI-generation or manipulation signals present, and the "
        "compression profile. Do NOT describe scene content or objects.\n"
        "  • Agent3 axis (object/scene): State what is depicted — subjects, objects, setting, UI "
        "elements — and any scene-level inconsistencies (shadow direction, scale, lighting anomalies). "
        "Do NOT describe pixel-level integrity or file metadata.\n"
        "  • Agent5 axis (metadata/provenance): State the concrete provenance record — capture "
        "timestamp, device make/model, software, GPS presence, field count — then any specific "
        "provenance contradiction found. NEVER open with a bare file-type label. "
        "Example: 'Captured 2024-03-14 07:32 UTC on a Pixel 7 (Android 14); "
        "GPS coordinates present; 847 EXIF fields intact — no anomalies detected.'\n\n"
        "FIELD 2 — agent_brief\n"
        "Exactly 2 sentences in the expert's voice. Dense, specific, no filler.\n"
        "  Sentence 1: Name the N checks that ran and their decisive outcomes, citing at least one "
        "concrete metric (e.g. '0 anomaly regions', 'SHA-256 confirmed', '14 EXIF fields stripped'). "
        "Do NOT restate the visual axis — that is Field 1's job.\n"
        "  Sentence 2: State the verdict and confidence in plain expert language that a court "
        "could read. Tie the confidence level to the specific signal pattern observed.\n"
        "FORBIDDEN in agent_brief: 'analysis complete', 'consistent with authenticity', "
        "'no anomalies detected', 'warrants further review' without specifying what.\n\n"
        "FIELD 3 — key_findings\n"
        "Up to 5 items (or empty if no findings apply). Each item covers ONE tool and must carry a specific metric.\n"
        "Format: [What the tool found, with the key metric] — [tool_name] ([confidence]%)\n"
        "Rules:\n"
        "  • Lead with the highest-impact finding (strongest positive signal first; if all clean, "
        "lead with the most definitive clean result).\n"
        "  • If a finding was grounded (severity adjusted because it is not applicable to this "
        "image type), say so: append '(context-adjusted)' after the tool name.\n"
        "  • Cite the ACTUAL metric number — e.g. '0 spliced blocks', 'hash matched', "
        "'14 EXIF fields stripped', '3 scene-inconsistency flags'.\n"
        "  • No two items may cover the same tool or the same forensic signal.\n"
        "  • You MUST ONLY cite tools that are explicitly provided in the 'findings' array. DO NOT invent or guess tool names like 'metadata_analysis' or 'deepfake_frequency_check' if they did not run.\n"
        "  • Do NOT include NOT_APPLICABLE or ERROR results — skip those tools entirely.\n"
        "  • Do NOT write: 'flagged a manipulation indicator', 'returned a positive result', "
        "'confirmed authenticity' — always state WHAT was measured and WHAT value it returned.\n\n"
        "━━━ OUTPUT SCHEMA (return exactly this, nothing else) ━━━\n"
        f"{schema_json}\n"
    )
    if is_deep:
        prompt += (
            "\n\n━━━ DEEP ANALYSIS MODE ━━━\n"
            "Each agent entry in the input includes 'phase1_verdict', 'phase1_confidence_pct', "
            "'deep_verdict', and 'deep_confidence_pct'. Findings are tagged with 'phase': 'initial' or 'deep'.\n"
            "Use this to populate the 'phase_comparison' field:\n"
            "  • Start with the delta keyword: CONFIRMED, REFINED, ESCALATED, or CONTRADICTED.\n"
            "  • CONFIRMED — same verdict, confidence within 10 pp.\n"
            "  • REFINED — same verdict bucket but confidence changed ≥10 pp, or INCONCLUSIVE → anything.\n"
            "  • ESCALATED — clean initial verdict, alert deep verdict.\n"
            "  • CONTRADICTED — alert initial verdict, clean deep verdict.\n"
            "  • State one concrete change or confirmation. No filler. Under 30 words."
        )
    return prompt


def _has_narratable_signal(inp: AgentSynthesisInput) -> bool:
    """True if this agent has a signal strong enough to warrant Groq narration.

    MEDIUM severity and below produces adequate deterministic synthesis — calling
    Groq for those findings only burns free-tier quota. We narrate only when the
    evidence is genuinely alarming (POSITIVE/alert verdicts, CRITICAL/HIGH severity,
    or confirmed visual anomalies from the visual-context profile).
    """
    _ALERT_VERDICTS = {"POSITIVE", "SUSPICIOUS", "TAMPERED", "MANIPULATED", "LIKELY_MANIPULATED"}
    for f in (inp.grounded_findings or inp.findings):
        verdict = str(f.get("evidence_verdict") or "").upper()
        if verdict in _ALERT_VERDICTS:
            return True
        meta = f.get("metadata") or {}
        severity = str(meta.get("severity_tier") or meta.get("severity") or "").upper()
        # MEDIUM and below: deterministic prose is sufficient — skip Groq.
        if severity in ("CRITICAL", "HIGH"):
            return True
    # Confirmed visual-context anomalies (not just "present" flags — require
    # non-empty signal lists so empty lists don't trigger the call).
    section = inp.visual_context_section or {}
    if isinstance(section, dict):
        for key in ("visible_manipulation_signals", "ai_generation_signals",
                    "scene_inconsistencies", "metadata_contradictions"):
            val = section.get(key)
            if val and (isinstance(val, list) and len(val) > 0 or isinstance(val, str) and val.strip()):
                return True
        assessment = str(section.get("integrity_assessment") or "").lower().strip()
        if assessment and assessment not in ("", "no_visible_issue", "cannot_determine", "authentic"):
            return True
    return False


# ── Synthesis result cache ───────────────────────────────────────────────────
# Keyed by a hash of the finding set (tool/verdict/confidence/severity tuples +
# per-agent verdicts). The same evidence re-analysed (re-runs, gate-2 retries,
# pre-warm → finalise) yields an identical deterministic basis, so the refined
# narrative can be reused with ZERO Groq tokens. Small in-module dict with a
# best-effort Redis layer (same pattern as gemini_client._DEEP_FORENSIC_CACHE +
# visual_context_store's Redis persistence).
_SYNTHESIS_CACHE: dict[str, dict[str, dict]] = {}
_SYNTHESIS_CACHE_MAX = 64
_SYNTHESIS_CACHE_TTL_S = 4 * 3600
_SYNTHESIS_CACHE_KEY_PREFIX = "synthesis_batch_v2:"


def _synthesis_cache_key(inputs: dict[str, AgentSynthesisInput]) -> str:
    """SHA-256 over the deterministic finding basis for this batch."""
    basis: dict[str, Any] = {}
    for aid in sorted(inputs.keys()):
        inp = inputs[aid]
        basis[aid] = {
            "findings": sorted(
                (
                    str((f.get("metadata") or {}).get("tool_name") or f.get("finding_type") or ""),
                    str(f.get("evidence_verdict") or ""),
                    str(f.get("confidence_raw") or (f.get("metadata") or {}).get("confidence") or ""),
                    str((f.get("metadata") or {}).get("severity_tier") or ""),
                )
                for f in (inp.grounded_findings or inp.findings)
            ),
            "verdict": inp.agent_verdict,
            "confidence": round(float(inp.agent_confidence or 0.0), 3),
            "deep": inp.is_deep_analysis,
        }
    blob = json.dumps(basis, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


async def _synthesis_cache_get(key: str) -> dict[str, dict] | None:
    cached = _SYNTHESIS_CACHE.get(key)
    if cached:
        return cached
    try:
        from core.persistence.redis_client import get_redis_client

        redis = await get_redis_client()
        value = await redis.get_json(f"{_SYNTHESIS_CACHE_KEY_PREFIX}{key}")
        if isinstance(value, dict) and value:
            _SYNTHESIS_CACHE[key] = value
            return value
    except Exception as exc:  # cache must never break synthesis
        logger.debug("Synthesis cache Redis read failed", error=str(exc))
    return None


async def _synthesis_cache_put(key: str, value: dict[str, dict]) -> None:
    if len(_SYNTHESIS_CACHE) >= _SYNTHESIS_CACHE_MAX:
        try:
            _SYNTHESIS_CACHE.pop(next(iter(_SYNTHESIS_CACHE)))
        except StopIteration:  # pragma: no cover
            pass
    _SYNTHESIS_CACHE[key] = value
    try:
        from core.persistence.redis_client import get_redis_client

        redis = await get_redis_client()
        await redis.set(f"{_SYNTHESIS_CACHE_KEY_PREFIX}{key}", value, ex=_SYNTHESIS_CACHE_TTL_S)
    except Exception as exc:  # cache must never break synthesis
        logger.debug("Synthesis cache Redis write failed", error=str(exc))


def _build_agent_entry(inp: AgentSynthesisInput) -> dict:
    """Build the per-agent prompt payload entry (shared by batch + individual paths).

    Findings are pre-summarised structured tuples (tool, verdict, confidence,
    severity, phase) — never raw tool prose — which both cuts tokens and removes
    the truncated-free-text hallucination source.
    """
    clean_findings = [
        {
            "tool": f.get("metadata", {}).get("tool_name") or f.get("finding_type"),
            "verdict": f.get("evidence_verdict"),
            "confidence": f.get("confidence_raw") or f.get("metadata", {}).get("confidence"),
            "severity": (f.get("metadata") or {}).get("severity_tier"),
            "phase": (f.get("metadata") or {}).get("analysis_phase", "initial"),
        }
        for f in (inp.grounded_findings or inp.findings)
        # Skip NOT_APPLICABLE and ERROR findings — they add no narrative value
        if str(f.get("evidence_verdict") or "").upper() not in ("NOT_APPLICABLE", "ERROR")
    ]
    entry: dict = {
        "agent_id": inp.agent_id,
        "evidence_identity": inp.evidence_identity,
        "visual_context_available": inp.visual_context_available,
        "visual_context_section": inp.visual_context_section,
        "completed_tools": inp.completed_tools,
        "failed_tools": inp.failed_tools,
        "findings": clean_findings,
        "agent_verdict": inp.agent_verdict,
        "agent_confidence": inp.agent_confidence,
        "confidence_reason": inp.confidence_reason,
    }
    if inp.is_deep_analysis and inp.phase1_verdict:
        entry["phase1_verdict"] = inp.phase1_verdict
        entry["phase1_confidence_pct"] = round(inp.phase1_confidence * 100)
        entry["deep_verdict"] = inp.agent_verdict
        entry["deep_confidence_pct"] = round(inp.agent_confidence * 100)
    return entry


def _apply_polished_agent(
    aid: str,
    polished_data: dict,
    outputs: dict[str, AgentSynthesisOutput],
    inputs: dict[str, AgentSynthesisInput],
) -> bool:
    """Validate + apply one agent's LLM-polished narrative fields.

    All verdict-consistency / fabricated-tool / degenerate-summary guards live
    here so the batched call and the individual fallback enforce identical
    court-defensibility rules. Returns True when the agent's synthesis was
    upgraded to groq_refined.
    """
    if aid not in outputs or not isinstance(polished_data, dict):
        return False
    _verdict = outputs[aid].agent_verdict
    # Real tool set for THIS agent — used to reject LLM-fabricated
    # key findings that cite a tool which never ran (e.g. a vision
    # model inventing "scene_geometry_analysis" / "lighting_analysis"
    # on a screenshot). Court-defensibility: a signed finding must
    # trace to an executed tool.
    _inp = inputs.get(aid)
    _agent_tools: set[str] = set()
    if _inp is not None:
        for _t in (_inp.completed_tools or []):
            _agent_tools.add(str(_t).lower())
        for _f in (_inp.grounded_findings or _inp.findings or []):
            _tn = (_f.get("metadata") or {}).get("tool_name") or _f.get("finding_type")
            if _tn:
                _agent_tools.add(str(_tn).lower())
    brief = polished_data.get("agent_brief")
    if brief and isinstance(brief, str):
        # Verdict is the single source of truth: reject a refined brief
        # that asserts manipulation while the verdict is clean/inconclusive.
        if _text_contradicts_verdict(brief, _verdict):
            logger.warning(
                f"{aid}: LLM brief contradicts verdict '{_verdict}'; keeping deterministic brief."
            )
        elif _is_echoed_instruction(brief):
            logger.warning(
                f"{aid}: LLM brief echoed prompt instructions; keeping deterministic brief."
            )
        elif _brief_misstates_verdict(brief, _verdict):
            logger.warning(
                f"{aid}: LLM brief assessment tier disagrees with verdict "
                f"'{_verdict}'; keeping deterministic brief."
            )
        else:
            outputs[aid].agent_brief = _round_pcts(brief)

    vc_sum = polished_data.get("visual_context_summary")
    _det_vc = outputs[aid].visual_context_summary
    if vc_sum and isinstance(vc_sum, str):
        if _text_contradicts_verdict(vc_sum, _verdict):
            logger.warning(
                f"{aid}: LLM visual_context_summary contradicts verdict "
                f"'{_verdict}'; keeping deterministic."
            )
        elif _is_degenerate_visual_summary(vc_sum, _det_vc):
            logger.warning(
                f"{aid}: LLM visual_context_summary collapsed to "
                f"{vc_sum!r}; keeping deterministic axis prose."
            )
        else:
            outputs[aid].visual_context_summary = _round_pcts(vc_sum)

    reason = polished_data.get("confidence_reason")
    if reason and isinstance(reason, str):
        outputs[aid].confidence_reason = _round_pcts(reason)

    kfs = polished_data.get("key_findings")
    if kfs and isinstance(kfs, list):
        seen_kf_norms: set[str] = set()
        validated_kfs: list[str] = []
        for kf in kfs:
            kf_str = str(kf).strip()
            if not kf_str:
                continue
            if _text_contradicts_verdict(kf_str, _verdict):
                logger.warning(
                    f"{aid}: key_finding contradicts verdict '{_verdict}'; dropped."
                )
                continue
            # Tool-grounding: a finding that attributes itself to a
            # specific tool slug must cite one this agent actually
            # ran. Drops hallucinated tools and context-only plumbing
            # that did NOT actually run (context-only tools that DID run
            # — e.g. visual_evidence_profile — are valid findings).
            _m = re.search(r"—\s*([a-z0-9]+(?:_[a-z0-9]+)+)\s*(?:\(\d+(?:\.\d+)?%\))?\s*$", kf_str)
            if _m:
                _cited = _m.group(1).lower()
                if _cited not in _agent_tools:
                    # Fuzzy alias: LLMs commonly hallucinate near-miss tool
                    # slugs (e.g. "timestamp_record" for "timestamp_analysis").
                    # Try a substring/overlap match against the real tool set
                    # before dropping the finding entirely.
                    _alias = _fuzzy_tool_alias(_cited, _agent_tools)
                    if _alias:
                        _cited = _alias
                        kf_str = kf_str[:_m.start(1)] + _alias + kf_str[_m.end(1):]
                    else:
                        logger.warning(
                            f"{aid}: key_finding cites tool '{_cited}' that did not run; dropped (fabricated)."
                        )
                        continue
                elif _cited in CONTEXT_ONLY_TOOLS:
                    # Context-only tool that actually ran — valid finding but
                    # remap to the friendly label so the report reads cleanly.
                    pass
                # The synthesis prompt asks the model to name the exact
                # tool, so it emits the raw slug ("frequency_domain_
                # analysis"). Swap in the friendly label for a
                # court-readable report.
                _label = TOOL_LABELS.get(_cited) or _cited.replace("_", " ").title()
                kf_str = kf_str[:_m.start(1)] + _label + kf_str[_m.end(1):]
            # Normalise the cited confidence "(NN%)": the model sometimes
            # emits the raw 0-1 fraction ("(0.297%)" → meant 30%) or
            # float-precision noise ("(39.999996%)"). A cited tool
            # confidence is never a genuine sub-1% value, so a value < 1
            # is a fraction to scale up; everything is rounded to an int.
            def _norm_conf_pct(m: re.Match[str]) -> str:
                v = float(m.group(1))
                if v < 1:
                    v *= 100
                return f"({round(v)}%)"
            kf_str = re.sub(r"\((\d+(?:\.\d+)?)%\)", _norm_conf_pct, kf_str)
            # Deduplicate: strip trailing confidence percentage before
            # normalising so near-identical findings that only differ in
            # the reported % (e.g. "tool (97%)" vs "tool (98%)") are
            # caught. Then take the first 80 chars as the dedup key.
            norm = re.sub(r"\s*\(\d+\.?\d*%\)\s*$", "", kf_str.lower())
            norm = re.sub(r"\s+", " ", norm).strip()[:80]
            if norm in seen_kf_norms:
                continue
            seen_kf_norms.add(norm)
            validated_kfs.append(kf_str)
        if validated_kfs:
            # Guarantee no MATERIAL signal is suppressed by the LLM's 3–5 cap or an
            # omission: the LLM key findings wholesale-replace the deterministic
            # ones, so a POSITIVE tool finding the model left out would vanish from
            # the report. Re-inject any positive (per the grounded finding set —
            # so grounding-cleared signals are not resurrected) that the LLM dropped.
            _inp_kf = inputs.get(aid)
            if _inp_kf is not None:
                _present_labels: set[str] = set()
                for _vk in validated_kfs:
                    _lm = re.search(r"—\s*([^—]+?)\s*(?:\(\d+%\))?\s*$", _vk)
                    if _lm:
                        _present_labels.add(re.sub(r"\s+", " ", _lm.group(1)).strip().lower())
                for _pf in (_inp_kf.grounded_findings or _inp_kf.findings or []):
                    if str(_pf.get("evidence_verdict") or "").upper() != "POSITIVE":
                        continue
                    _ptid = str((_pf.get("metadata") or {}).get("tool_name") or _pf.get("finding_type") or "")
                    if not _ptid or _ptid in CONTEXT_ONLY_TOOLS:
                        continue
                    _plabel = TOOL_LABELS.get(_ptid, _ptid.replace("_", " ").title())
                    if _plabel.strip().lower() in _present_labels:
                        continue
                    _pline = format_finding_first(_pf)
                    if _text_contradicts_verdict(_pline, _verdict):
                        continue
                    validated_kfs.append(_pline)
                    _present_labels.add(_plabel.strip().lower())
                    logger.warning(
                        f"{aid}: LLM dropped POSITIVE finding for tool '{_ptid}'; re-injected to prevent suppression."
                    )
            outputs[aid].key_findings = validated_kfs

    # phase_comparison — deep-mode only; stored on the output for
    # the arbiter to surface in per_agent_narrative_structured.
    pc = polished_data.get("phase_comparison")
    if pc and isinstance(pc, str) and len(pc.strip()) > 10:
        outputs[aid].phase_comparison = pc.strip()

    outputs[aid].synthesis_source = "groq_refined"
    logger.info(f"Refined synthesis for {aid} using LLM.")
    return True


async def _refine_individual_fallback(
    llm_client: LLMClient,
    inputs: dict[str, AgentSynthesisInput],
    outputs: dict[str, AgentSynthesisOutput],
    is_deep: bool,
    investigation_id: str = "",
) -> None:
    """EXPLICIT FALLBACK ONLY: per-agent individual synthesis calls.

    The batched call is the sole primary path; this runs only when the batch
    Groq call failed (timeout / parse error / empty response). Each narratable
    agent gets one small single-agent call under the same persona prompt and
    the same validation, still subject to the per-investigation token budget.
    """
    for aid, inp in inputs.items():
        if aid not in outputs or not _has_narratable_signal(inp):
            continue
        if outputs[aid].synthesis_source == "groq_refined":
            continue
        system_prompt = _build_persona_system_prompt([aid], is_deep=is_deep)
        user_payload = json.dumps({aid: _build_agent_entry(inp)}, indent=2, default=str)
        if investigation_id:
            from core.quota_manager import get_investigation_budget

            estimated = (len(system_prompt) + len(user_payload)) // 4 + 400
            allowed, reason = await get_investigation_budget(investigation_id).try_consume(
                estimated, job="synthesis"
            )
            if not allowed:
                outputs[aid].synthesis_source = "deterministic_template"
                logger.warning(
                    f"{aid}: individual synthesis fallback rejected by token budget: {reason}"
                )
                continue
        try:
            raw = await asyncio.wait_for(
                llm_client.generate_synthesis(
                    system_prompt=system_prompt,
                    user_content=user_payload,
                    json_mode=True,
                    priority="medium",
                    max_tokens=400,
                ),
                timeout=25.0,
            )
            if not raw:
                continue
            parsed = json.loads(LLMClient._strip_markdown_fences(raw))
            polished = parsed.get(aid) if isinstance(parsed, dict) else None
            if not isinstance(polished, dict) and isinstance(parsed, dict):
                polished = parsed  # model returned the agent object directly
            if isinstance(polished, dict):
                _apply_polished_agent(aid, polished, outputs, inputs)
        except Exception as exc:
            logger.warning(f"Individual synthesis fallback failed for {aid}: {exc}")


async def refine_synthesis_batch(
    inputs: dict[str, AgentSynthesisInput],
    config: Settings,
    investigation_id: str = "",
) -> dict[str, AgentSynthesisOutput]:
    """Single batched synthesis refiner.

    Constructs one Groq prompt covering all three agents with per-agent expert
    persona voices, makes one LLM call, and falls back to deterministic output
    on any failure. The deterministic fallback is always pre-built first so the
    function never blocks.
    """
    outputs = {}

    # 1. Build deterministic syntheses first — these are the fallback AND the
    #    foundation: numeric values (verdict, confidence) come from here and the
    #    LLM is only allowed to touch the narrative fields.
    for aid, inp in inputs.items():
        outputs[aid] = generate_deterministic_agent_synthesis(inp)

    # 2. Guard: skip LLM refinement if not configured
    llm_client = LLMClient(config=config)
    if not (config.llm_enable_post_synthesis and config.llm_api_key and llm_client.is_available):
        logger.info(
            "Groq per-agent synthesis skipped (LLM disabled/unavailable).",
            post_synthesis_enabled=bool(config.llm_enable_post_synthesis),
            has_api_key=bool(config.llm_api_key),
            provider=getattr(config, "llm_provider", None),
            client_available=llm_client.is_available,
        )
        return outputs

    # 2b. Clean-evidence early-exit: if NO agent has a narratable signal, the
    #     deterministic synthesis is already optimal. Skip the Groq call to
    #     preserve free-tier quota — this is the common clean-screenshot case.
    if not any(_has_narratable_signal(inp) for inp in inputs.values()):
        logger.info(
            "Groq per-agent synthesis skipped — all agents clean (no narratable signal); "
            "deterministic output is sufficient.",
            agents=list(inputs.keys()),
        )
        return outputs

    logger.info(
        "Groq per-agent synthesis invoked.",
        agents=[aid for aid, inp in inputs.items() if _has_narratable_signal(inp)],
    )

    # 3. Build the per-agent payload (pre-summarised structured tuples — the
    #    verbose reasoning_summary prose is intentionally never sent).
    is_deep = any(inp.is_deep_analysis for inp in inputs.values())

    batch_prompt_data = {aid: _build_agent_entry(inp) for aid, inp in inputs.items()}

    system_prompt = _build_persona_system_prompt(list(inputs.keys()), is_deep=is_deep)
    user_payload = json.dumps(batch_prompt_data, indent=2, default=str)

    # 3b. Synthesis cache — identical finding set ⇒ reuse the refined narrative
    #     with zero Groq tokens.
    cache_key = _synthesis_cache_key(inputs)
    cached = await _synthesis_cache_get(cache_key)
    if cached:
        applied = 0
        for aid, fields in cached.items():
            out = outputs.get(aid)
            if out is None or not isinstance(fields, dict):
                continue
            if fields.get("agent_brief"):
                out.agent_brief = str(fields["agent_brief"])
            if fields.get("visual_context_summary"):
                out.visual_context_summary = str(fields["visual_context_summary"])
            if fields.get("confidence_reason"):
                out.confidence_reason = str(fields["confidence_reason"])
            if isinstance(fields.get("key_findings"), list) and fields["key_findings"]:
                out.key_findings = [str(k) for k in fields["key_findings"]]
            if fields.get("phase_comparison"):
                out.phase_comparison = str(fields["phase_comparison"])
            out.synthesis_source = "groq_refined"
            applied += 1
        if applied:
            logger.info(
                "Per-agent synthesis cache hit — reused refined narrative (no Groq call).",
                agents=list(cached.keys()),
            )
            return outputs

    # 3c. Per-investigation token budget: never let synthesis invade the
    #     refiner reserve. On rejection the deterministic template is the
    #     result and carries the provenance tag.
    if investigation_id:
        from core.quota_manager import get_investigation_budget

        estimated_tokens = (len(system_prompt) + len(user_payload)) // 4 + 1000
        allowed, reason = await get_investigation_budget(investigation_id).try_consume(
            estimated_tokens, job="synthesis"
        )
        if not allowed:
            for out in outputs.values():
                out.synthesis_source = "deterministic_template"
            logger.warning(
                f"Per-agent synthesis rejected by investigation token budget: {reason}. "
                "Using deterministic template.",
                investigation_id=investigation_id,
            )
            try:
                from api.routes.metrics import increment_synthesis_degradation

                increment_synthesis_degradation(len(outputs))
            except Exception:  # noqa: S110 - metrics must never break synthesis
                pass
            return outputs

    batch_failed = False
    try:
        # Hard ceiling on the Groq refinement so a rate-limited/slow run can never
        # block the arbiter deliberation — the deterministic outputs are already
        # built above and used as-is on timeout.
        raw_response = await asyncio.wait_for(
            llm_client.generate_synthesis(
                system_prompt=system_prompt,
                user_content=user_payload,
                json_mode=True,
                priority="medium",
                # One JSON object covering every active agent (visual_context_summary
                # + agent_brief + 3–5 key_findings each). 900 was too tight once
                # findings are present — the model can hit the completion limit
                # mid-JSON and Groq rejects the whole call with `json_validate_failed`.
                max_tokens=1400,
            ),
            timeout=40.0,
        )
        if raw_response:
            cleaned_resp = raw_response.strip()
            if cleaned_resp.startswith("```"):
                lines = cleaned_resp.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                cleaned_resp = "\n".join(lines).strip()

            parsed = json.loads(cleaned_resp)
            for aid in ("Agent1", "Agent2", "Agent3", "Agent4", "Agent5"):
                if aid in parsed and aid in outputs:
                    _apply_polished_agent(aid, parsed[aid], outputs, inputs)
        else:
            batch_failed = True
    except TimeoutError:
        batch_failed = True
        logger.warning("Groq per-agent synthesis timed out (40s) — trying individual fallback.")
    except Exception as e:
        batch_failed = True
        logger.warning(f"Batched synthesis refinement failed or rejected: {e}.")
        # Deterministic fallbacks are already populated in outputs

    # Individual per-agent path — EXPLICIT fallback, used only when the batch
    # call failed. Same prompts/validation, one small call per narratable agent.
    if batch_failed:
        await _refine_individual_fallback(
            llm_client, inputs, outputs, is_deep, investigation_id=investigation_id
        )

    # Cache the refined narrative fields keyed by the finding-set hash so an
    # identical re-run costs zero Groq tokens.
    refined_fields = {
        aid: {
            "agent_brief": out.agent_brief,
            "visual_context_summary": out.visual_context_summary,
            "key_findings": list(out.key_findings),
            "confidence_reason": out.confidence_reason,
            "phase_comparison": out.phase_comparison,
        }
        for aid, out in outputs.items()
        if getattr(out, "synthesis_source", "") == "groq_refined"
    }
    if refined_fields:
        await _synthesis_cache_put(cache_key, refined_fields)

    # WS-6 #30: refinement was ATTEMPTED (guards above passed) — every agent
    # that still carries the deterministic synthesis here degraded. Intentional
    # skips (LLM disabled, clean evidence) returned earlier and are not counted.
    _degraded = sum(
        1 for out in outputs.values() if getattr(out, "synthesis_source", "") != "groq_refined"
    )
    if _degraded:
        try:
            from api.routes.metrics import increment_synthesis_degradation

            increment_synthesis_degradation(_degraded)
        except Exception:  # noqa: S110 - metrics must never break synthesis
            pass

    return outputs
