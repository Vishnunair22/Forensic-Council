from __future__ import annotations

import asyncio
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
    agent_id: Literal["Agent1", "Agent3", "Agent5"]
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


class AgentSynthesisOutput(BaseModel):
    agent_id: str
    agent_brief: str
    visual_context_summary: str = ""
    key_findings: list[str] = Field(default_factory=list)
    agent_verdict: str
    confidence_score: float
    confidence_reason: str = ""
    limitations: list[str] = Field(default_factory=list)
    synthesis_source: Literal[
        "groq_refined",
        "deterministic_with_visual_context",
        "deterministic_tool_only",
        "groq_tool_only"
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
        # Alert verdict driven by the holistic visual read, not a discrete tool
        # POSITIVE. Lead with the holistic signal so the key findings do not read
        # as all-clean beside a SUSPICIOUS/MANIPULATED verdict.
        key_findings = [
            "The holistic visual assessment flagged this evidence as anomalous; see Visual "
            "Context for the contributing read."
        ] + _clean[:4]
    elif _clean:
        # Clean path: the evidence is benign — surface the substantive clean
        # findings themselves (now richly described) so the section is informative
        # rather than a bare "nothing found" line.
        key_findings = _clean[:5]
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
        "Agent3": "no distinct object or scene context was observed",
        "Agent5": "no distinct visual metadata or provenance clues were observed",
    }.get(input_data.agent_id, "no distinct visual context was observed")

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
    _n_checks = len(input_data.completed_tools) or len(_source_findings)
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
        agent_brief = (
            f"The {_axis_label} examination completed {_n_checks} check(s). No individual "
            f"tool isolated a discrete manipulation signal, but the holistic assessment is "
            f"anomalous (see Visual Context for the contributing read)."
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
    if input_data.agent_verdict:
        _vv = str(input_data.agent_verdict).replace("_", " ").title()
        _cc = int(round(float(input_data.agent_confidence or 0.0) * 100))
        agent_brief += f" Verdict: {_vv} ({_cc}% confidence)."

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
        confidence_reason = (
            f"No discrete tool isolated a manipulation signal, but the holistic visual "
            f"assessment supports {_art} {_vw or 'suspicious'} finding across "
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
_CLEAN_VERDICTS = {"AUTHENTIC", "INCONCLUSIVE", "NEGATIVE", "NOT_APPLICABLE", "CLEAN", ""}


def _text_contradicts_verdict(text: str, verdict: str) -> bool:
    """True if narrative text asserts manipulation while the deterministic verdict
    is clean/inconclusive. Used to reject contradictory LLM narrative and keep the
    deterministic text, so findings never disagree with the verdict."""
    if not text:
        return False
    if str(verdict or "").upper() not in _CLEAN_VERDICTS:
        return False  # alert verdicts may legitimately use manipulation language
    low = text.lower()
    return any(term in low for term in _MANIPULATION_TERMS)


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
    if len(base) >= 60 and len(text.strip()) < 0.35 * len(base):
        return True
    return False


def _build_persona_system_prompt(agent_ids: list[str]) -> str:
    """
    Build the Groq system prompt with per-agent expert voice instructions.
    The persona voice definitions are the single source of truth — they live
    in agent_personas.py and are injected here at call time so a change to
    a persona definition automatically propagates to the synthesis prompt.
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

    return (
        "You are a forensic narrative specialist writing expert testimony for a multi-agent "
        "digital evidence analysis system. Each agent has a distinct expert identity. "
        "Write ONLY in their assigned voice — not in generic template language.\n\n"
        + persona_section
        + "\n\n"
        "INVIOLABLE CONSTRAINTS — these override everything else:\n"
        "1. NEVER change 'agent_verdict' or 'agent_confidence' — these are deterministic forensic "
        "measurements. They are facts, not opinions.\n"
        "2. NEVER mention any tool vendor, AI provider, or model name "
        "(Gemini, Groq, Cerebras, OpenAI, Llama, Google, CLIP, YOLO, etc.).\n"
        "3. NEVER treat a missing API key or unavailable model as a degradation. "
        "Only actual tool execution failures may appear as limitations.\n"
        "4. Every key finding MUST follow this format: "
        "[Finding statement] — [Tool name] ([Confidence]%)\n"
        "5. Write in the present tense. The analysis has been completed; report its findings.\n"
        "6. Return ONLY valid JSON — no markdown, no prose outside the JSON.\n"
        "7. SEPARATE the two fields cleanly — they must NOT repeat each other. Each agent's "
        "'visual_context_summary' is written from ITS OWN visual axis in 'visual_context_section' — "
        "NEVER from a generic image/scene description:\n"
        "   - Agent1 (image integrity): lead with the integrity read — file type as a forensic "
        "attribute, the holistic authenticity assessment, and any visible manipulation / AI-generation "
        "/ compression signals. Do NOT describe the scene; that is Agent3's axis.\n"
        "   - Agent3 (object/scene): lead with the scene and object inventory — what is depicted, "
        "objects, people, UI elements, and any scene inconsistencies.\n"
        "   - Agent5 (metadata/provenance): lead with the concrete provenance facts — capture "
        "timestamp, device, file format and size, field count, GPS — then any provenance "
        "contradictions. NEVER lead with a bare file-type word (e.g. 'a composite image').\n"
        "   - 'agent_brief' is the ANALYTICAL OVERVIEW: summarize the tools/checks that ran and the "
        "verdict reached, in the expert's voice. Do NOT restate the visual axis here.\n"
        "8. CONSISTENCY WITH VERDICT IS MANDATORY. The narrative MUST agree with 'agent_verdict'. "
        "If agent_verdict is AUTHENTIC or INCONCLUSIVE, do NOT assert or imply the evidence is "
        "manipulated, tampered, forged, fabricated, doctored, spliced, deepfaked, AI-generated, or "
        "fake — describe results as clean, benign, or inconclusive. If agent_verdict is SUSPICIOUS or "
        "MANIPULATED, do NOT claim the evidence is authentic or unaltered. Never contradict the verdict.\n\n"
        "Schema:\n"
        "{\n"
        "  \"Agent1\": {\n"
        "    \"agent_brief\": \"<2-3 sentence expert overview of the checks that ran and the verdict, in Agent1 voice>\",\n"
        "    \"visual_context_summary\": \"<1-2 sentences on the IMAGE-INTEGRITY axis: file type, authenticity read, manipulation/AI/compression signals — never a scene description>\",\n"
        "    \"key_findings\": [\"<Finding> — <Tool> (<Conf>%)\", ...],\n"
        "    \"confidence_reason\": \"<1 sentence on why the confidence level is justified>\",\n"
        "    \"limitations\": [\"<only real tool failures>\"]\n"
        "  },\n"
        "  \"Agent3\": { \"visual_context_summary\": \"<scene + object inventory + inconsistencies>\", ... },\n"
        "  \"Agent5\": { \"visual_context_summary\": \"<provenance facts: timestamp, device, format, size, GPS; never a bare file-type word>\", ... }\n"
        "}"
    )


def _has_narratable_signal(inp: AgentSynthesisInput) -> bool:
    """True if this agent has anything worth a Groq-polished narrative.

    Clean evidence (no positive/alert findings, no visual anomalies) produces
    a perfectly adequate deterministic synthesis — calling Groq for it only
    burns quota. We narrate only when there is a real signal to articulate.
    """
    _ALERT_VERDICTS = {"POSITIVE", "SUSPICIOUS", "TAMPERED", "MANIPULATED", "LIKELY_MANIPULATED"}
    for f in (inp.grounded_findings or inp.findings):
        verdict = str(f.get("evidence_verdict") or "").upper()
        if verdict in _ALERT_VERDICTS:
            return True
        meta = f.get("metadata") or {}
        severity = str(meta.get("severity_tier") or meta.get("severity") or "").upper()
        if severity in ("CRITICAL", "HIGH", "MEDIUM"):
            return True
    # Visual-context anomalies are narratable even when tools are clean
    section = inp.visual_context_section or {}
    if isinstance(section, dict):
        for key in ("visible_manipulation_signals", "ai_generation_signals", "scene_inconsistencies", "metadata_contradictions"):
            if section.get(key):
                return True
        if str(section.get("integrity_assessment") or "").lower() not in ("", "no_visible_issue", "cannot_determine"):
            return True
    # Tool failures are worth narrating as limitations
    return bool(inp.failed_tools)


async def refine_synthesis_batch(
    inputs: dict[str, AgentSynthesisInput],
    config: Settings,
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

    # 3. Build the per-agent payload
    batch_prompt_data = {}
    for aid, inp in inputs.items():
        clean_findings = [
            {
                "tool": f.get("metadata", {}).get("tool_name") or f.get("finding_type"),
                "summary": f.get("reasoning_summary") or f.get("metadata", {}).get("summary"),
                "verdict": f.get("evidence_verdict"),
                "confidence": f.get("confidence_raw") or f.get("metadata", {}).get("confidence"),
            }
            for f in (inp.grounded_findings or inp.findings)
        ]
        batch_prompt_data[aid] = {
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

    system_prompt = _build_persona_system_prompt(list(inputs.keys()))
    user_payload = json.dumps(batch_prompt_data, indent=2, default=str)

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
                # Three short expert briefs — 1200 tokens is ample and keeps the
                # call well within free-tier TPM limits.
                max_tokens=1200,
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
            for aid in ("Agent1", "Agent3", "Agent5"):
                if aid in parsed and aid in outputs:
                    polished_data = parsed[aid]
                    _verdict = outputs[aid].agent_verdict
                    brief = polished_data.get("agent_brief")
                    if brief and isinstance(brief, str):
                        # Verdict is the single source of truth: reject a refined brief
                        # that asserts manipulation while the verdict is clean/inconclusive.
                        if _text_contradicts_verdict(brief, _verdict):
                            logger.warning(
                                f"{aid}: LLM brief contradicts verdict '{_verdict}'; keeping deterministic brief."
                            )
                        else:
                            outputs[aid].agent_brief = brief

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
                            outputs[aid].visual_context_summary = vc_sum

                    reason = polished_data.get("confidence_reason")
                    if reason and isinstance(reason, str):
                        outputs[aid].confidence_reason = reason

                    kfs = polished_data.get("key_findings")
                    if kfs and isinstance(kfs, list):
                        validated_kfs = [
                            kf_str
                            for kf in kfs
                            if (kf_str := str(kf).strip())
                            and not _text_contradicts_verdict(kf_str, _verdict)
                        ]
                        if validated_kfs:
                            outputs[aid].key_findings = validated_kfs

                    outputs[aid].synthesis_source = "groq_refined"
                    logger.info(f"Refined synthesis for {aid} using LLM.")
    except TimeoutError:
        logger.warning("Groq per-agent synthesis timed out (40s) — using deterministic fallbacks.")
    except Exception as e:
        logger.warning(f"Batched synthesis refinement failed or rejected: {e}. Using deterministic fallbacks.")
        # Fallbacks are already populated in outputs

    return outputs
