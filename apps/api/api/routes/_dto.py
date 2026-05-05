"""
DTO Conversion Helpers
======================

Helpers for converting ForensicReport and findings to serialization-safe DTOs.
"""

from typing import Any

from api.schemas import AgentFindingDTO, ReportDTO
from core.severity import assign_severity_tier as _assign_severity_tier
from core.structured_logging import get_logger

logger = get_logger(__name__)


def _opt_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _forensic_report_to_dto(report) -> ReportDTO:
    """
    Convert a ForensicReport Pydantic model or dict to a serialization-safe ReportDTO.
    """

    def _get_val(obj, key, default=None):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def _as_dict(f) -> dict:
        if isinstance(f, dict):
            return f
        if hasattr(f, "model_dump"):
            return f.model_dump(mode="json")
        if hasattr(f, "__dict__"):
            return vars(f)
        return {}

    def _to_finding_dto(f) -> AgentFindingDTO:
        d = _as_dict(f)
        meta = d.get("metadata") or {}
        if isinstance(meta, str):
            try:
                import json as _json

                meta = _json.loads(meta)
            except Exception:
                meta = {}

        evidence_verdict = str(
            d.get("evidence_verdict") or meta.get("evidence_verdict") or "INCONCLUSIVE"
        ).upper()
        if evidence_verdict not in {
            "POSITIVE",
            "NEGATIVE",
            "INCONCLUSIVE",
            "NOT_APPLICABLE",
            "ERROR",
        }:
            evidence_verdict = "INCONCLUSIVE"

        dto = AgentFindingDTO(
            finding_id=str(d.get("finding_id", "")),
            agent_id=str(d.get("agent_id", "")),
            agent_name=str(d.get("agent_name", d.get("agent_id", ""))),
            finding_type=str(d.get("finding_type", "Unknown")),
            status=str(d.get("status", "CONFIRMED")),
            confidence_raw=_opt_float(d.get("confidence_raw")),
            evidence_verdict=evidence_verdict,  # type: ignore[arg-type]
            calibrated=bool(d.get("calibrated", False)),
            calibrated_probability=_opt_float(d.get("calibrated_probability")),
            raw_confidence_score=_opt_float(d.get("raw_confidence_score"))
            or _opt_float(d.get("confidence_raw")),
            calibration_status=str(d.get("calibration_status", "UNCALIBRATED")),
            court_statement=d.get("court_statement") or meta.get("court_statement"),
            robustness_caveat=bool(d.get("robustness_caveat", False)),
            robustness_caveat_detail=d.get("robustness_caveat_detail"),
            reasoning_summary=str(d.get("reasoning_summary") or ""),
            metadata=meta if meta else None,
        )
        dto.severity_tier = _assign_severity_tier(d)
        return dto

    def _is_real_finding(f) -> bool:
        d = _as_dict(f)
        summary = str(d.get("reasoning_summary") or "")
        ftype = str(d.get("finding_type") or "")
        if not summary and not ftype:
            return False
        if ftype.lower() in ("file type not applicable", "format not supported"):
            return False
        return True

    per_agent: dict = {}
    paf = _get_val(report, "per_agent_findings", {})
    for agent_id, findings in (paf or {}).items():
        try:
            real = [_to_finding_dto(f) for f in findings if _is_real_finding(f)]
            if real:
                per_agent[agent_id] = real
        except Exception as e:
            logger.warning(
                "Failed to convert findings for agent",
                agent_id=agent_id,
                error=str(e),
            )

    cross_modal = []
    try:
        cmc = _get_val(report, "cross_modal_confirmed", [])
        cross_modal = [_to_finding_dto(f) for f in (cmc or []) if _is_real_finding(f)]
    except Exception as e:
        logger.warning("Failed to convert cross-modal findings", error=str(e))

    incomplete = []
    try:
        inc = _get_val(report, "incomplete_findings", [])
        incomplete = [_to_finding_dto(f) for f in (inc or []) if _is_real_finding(f)]
    except Exception as e:
        logger.warning("Failed to convert incomplete findings", error=str(e))

    tribunal_resolved = []
    tr = _get_val(report, "tribunal_resolved", [])
    for item in tr or []:
        try:
            if hasattr(item, "model_dump"):
                tribunal_resolved.append(item.model_dump(mode="json"))
            elif isinstance(item, dict):
                tribunal_resolved.append(item)
        except Exception as e:
            logger.warning("Failed to serialize tribunal case", error=str(e))

    contested = []
    cf = _get_val(report, "contested_findings", [])
    for item in cf or []:
        try:
            if hasattr(item, "model_dump"):
                contested.append(item.model_dump(mode="json"))
            elif isinstance(item, dict):
                contested.append(item)
        except Exception as e:
            logger.warning("Failed to serialize contested finding", error=str(e))

    signed_utc_str: str | None = None
    s_utc = _get_val(report, "signed_utc")
    if s_utc is not None:
        try:
            if hasattr(s_utc, "isoformat"):
                signed_utc_str = s_utc.isoformat()
            else:
                signed_utc_str = str(s_utc)
        except Exception as e:
            logger.warning("Failed to serialize signed_utc", error=str(e))
            signed_utc_str = None

    return ReportDTO(
        report_id=str(_get_val(report, "report_id", "")),
        session_id=str(_get_val(report, "session_id", "")),
        case_id=_get_val(report, "case_id", ""),
        executive_summary=_get_val(report, "executive_summary", "") or "",
        per_agent_findings=per_agent,
        per_agent_metrics=_get_val(report, "per_agent_metrics", {}) or {},
        per_agent_analysis=_get_val(report, "per_agent_analysis", {}) or {},
        overall_confidence=float(_get_val(report, "overall_confidence", 0.0) or 0.0),
        overall_error_rate=float(_get_val(report, "overall_error_rate", 0.0) or 0.0),
        overall_verdict=str(_get_val(report, "overall_verdict", "REVIEW REQUIRED") or "REVIEW REQUIRED"),
        cross_modal_confirmed=cross_modal,
        contested_findings=contested,
        tribunal_resolved=tribunal_resolved,
        incomplete_findings=incomplete,
        uncertainty_statement=_get_val(report, "uncertainty_statement", "") or "",
        cryptographic_signature=_get_val(report, "cryptographic_signature", "") or "",
        report_hash=_get_val(report, "report_hash", "") or "",
        signed_utc=signed_utc_str,
        verdict_sentence=_get_val(report, "verdict_sentence", "") or "",
        key_findings=list(_get_val(report, "key_findings", []) or []),
        reliability_note=_get_val(report, "reliability_note", "") or "",
        manipulation_probability=float(_get_val(report, "manipulation_probability", 0.0) or 0.0),
        compression_penalty=float(_get_val(report, "compression_penalty", 1.0) or 1.0),
        confidence_min=float(_get_val(report, "confidence_min", 0.0) or 0.0),
        confidence_max=float(_get_val(report, "confidence_max", 0.0) or 0.0),
        confidence_std_dev=float(_get_val(report, "confidence_std_dev", 0.0) or 0.0),
        applicable_agent_count=int(_get_val(report, "applicable_agent_count", 0) or 0),
        skipped_agents=dict(_get_val(report, "skipped_agents", {}) or {}),
        analysis_coverage_note=_get_val(report, "analysis_coverage_note", "") or "",
        per_agent_summary=dict(_get_val(report, "per_agent_summary", {}) or {}),
        degradation_flags=list(_get_val(report, "degradation_flags", []) or []),
        cross_modal_fusion=dict(_get_val(report, "cross_modal_fusion", {}) or {}),
    )


def _rebuild_finding(f: dict) -> AgentFindingDTO:
    metadata = f.get("metadata") or {}
    evidence_verdict = str(
        f.get("evidence_verdict") or metadata.get("evidence_verdict") or "INCONCLUSIVE"
    ).upper()
    if evidence_verdict not in {
        "POSITIVE",
        "NEGATIVE",
        "INCONCLUSIVE",
        "NOT_APPLICABLE",
        "ERROR",
    }:
        evidence_verdict = "INCONCLUSIVE"
    dto = AgentFindingDTO(
        finding_id=str(f.get("finding_id", "")),
        agent_id=str(f.get("agent_id", "")),
        agent_name=str(f.get("agent_name", "")),
        finding_type=str(f.get("finding_type", "")),
        status=str(f.get("status", "CONFIRMED")),
        confidence_raw=_opt_float(f.get("confidence_raw")),
        evidence_verdict=evidence_verdict,  # type: ignore[arg-type]
        calibrated=bool(f.get("calibrated", False)),
        calibrated_probability=_opt_float(f.get("calibrated_probability")),
        raw_confidence_score=_opt_float(f.get("raw_confidence_score"))
        or _opt_float(f.get("confidence_raw")),
        calibration_status=str(f.get("calibration_status", "UNCALIBRATED")),
        court_statement=f.get("court_statement"),
        robustness_caveat=bool(f.get("robustness_caveat", False)),
        robustness_caveat_detail=f.get("robustness_caveat_detail"),
        reasoning_summary=str(f.get("reasoning_summary", "")),
        metadata=metadata or None,
    )
    dto.severity_tier = _assign_severity_tier(dto)
    return dto
