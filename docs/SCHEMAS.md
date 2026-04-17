# Forensic Council â€” Data Schemas

**Version:** v1.3.0 | Pydantic (backend) and TypeScript (frontend) models.

---

## AgentFindingDTO

Single conclusion from one of the 5 forensic agents.

```json
{
  "finding_id": "uuid",
  "agent_id": "Agent1",
  "agent_name": "Image Forensics",
  "finding_type": "ela_full_image",
  "status": "CONFIRMED",
  "confidence_raw": 0.94,
  "calibrated": true,
  "calibrated_probability": 0.88,
  "court_statement": "Region at (120,400) shows quantization matrices distinct from background â€” consistent with post-capture compositing.",
  "robustness_caveat": false,
  "robustness_caveat_detail": null,
  "reasoning_summary": "ELA anomaly map shows bright patches in the upper-right quadrant indicating a different JPEG save history from the rest of the image.",
  "metadata": {
    "tool_name": "ela_full_image",
    "court_defensible": true,
    "analysis_phase": "initial",
    "analysis_source": "classical_tools"
  }
}
```

**Key fields:**
- `confidence_raw` â€” ML tool output score (0.0â€“1.0)
- `calibrated_probability` â€” Platt-scaled probability; `null` if not calibrated
- `court_statement` â€” court-admissible language produced by the calibration layer
- `metadata.analysis_phase` â€” `"initial"` or `"deep"` (deep findings include Gemini vision)
- `metadata.analysis_source` â€” `"classical_tools"` or `"gemini_vision"`
- `metadata.court_defensible` â€” whether the finding meets evidentiary standards

---

## AgentMetricsDTO

Per-agent performance metrics for the result page.

```json
{
  "agent_id": "Agent1",
  "agent_name": "Image Forensics",
  "total_tools_called": 8,
  "tools_succeeded": 7,
  "tools_failed": 1,
  "error_rate": 0.125,
  "confidence_score": 0.87,
  "finding_count": 5,
  "skipped": false
}
```

---

## ReportDTO

Full signed investigation report returned by `GET /api/v1/sessions/{id}/report`.

```json
{
  "report_id": "uuid",
  "session_id": "uuid",
  "case_id": "CASE-20260101-001",
  "executive_summary": "The uploaded media contains multiple high-confidence manipulation indicators...",

  "per_agent_findings": {
    "Agent1": [ ...AgentFindingDTO... ],
    "Agent3": [ ...AgentFindingDTO... ],
    "Agent5": [ ...AgentFindingDTO... ]
  },

  "per_agent_metrics": {
    "Agent1": { ...AgentMetricsDTO... },
    "Agent3": { ...AgentMetricsDTO... }
  },

  "per_agent_analysis": {
    "Agent1": "Image Forensics found strong ELA anomalies during initial pass. Deep analysis confirmed via Gemini vision that the upper-right quadrant was composited from a different source image...",
    "Agent3": "Object detection identified 3 firearms in scene. Lighting consistency analysis shows shadow direction inconsistent with claimed outdoor noon timestamp..."
  },

  "overall_confidence": 0.89,
  "overall_error_rate": 0.08,
  "overall_verdict": "MANIPULATION DETECTED",

  "cross_modal_confirmed": [ ...AgentFindingDTO... ],
  "contested_findings": [ ...FindingComparison objects... ],
  "tribunal_resolved": [ ...TribunalCase objects... ],
  "incomplete_findings": [ ...AgentFindingDTO... ],

  "uncertainty_statement": "Analysis is limited by the lossy JPEG compression applied before upload. Spectral analysis confidence may be overstated for files with multiple re-encoding events.",
  "cryptographic_signature": "3045022100a3f1...hex...",
  "report_hash": "e3b0c44298fc1c149afbf4c8996fb924...",
  "signed_utc": "2026-03-16T14:32:00.000000+00:00"
}
```

**Overall verdict values:**
| Verdict | Meaning |
|---------|---------|
| `CERTAIN` | â‰¥ 80% confidence, â‰¤ 10% error rate, no contested findings |
| `LIKELY` | â‰¥ 65% confidence, â‰¤ 20% error rate |
| `UNCERTAIN` | â‰¥ 50% confidence or â‰¤ 3 contested findings |
| `INCONCLUSIVE` | < 50% confidence and > 40% error rate |
| `MANIPULATION DETECTED` | â‰¥ 2 agents flagged manipulation/deepfake/splice keywords |
| `REVIEW REQUIRED` | Default fallback |

---

## InvestigationResponse

Returned immediately after `POST /api/v1/investigate`.

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "case_id": "CASE-20260101-001",
  "status": "started",
  "message": "Investigation started for evidence.jpg"
}
```

---

## HITLDecisionRequest

Body for `POST /api/v1/hitl/decision`.

```json
{
  "session_id": "uuid",
  "checkpoint_id": "uuid",
  "agent_id": "Agent3",
  "decision": "APPROVE",
  "note": "Optional investigator comment",
  "override_finding": null
}
```

**Decision values:** `APPROVE` Â· `REDIRECT` Â· `OVERRIDE` Â· `TERMINATE` Â· `ESCALATE`

---

## BriefUpdate (WebSocket message)

All WebSocket messages share this shape.

```json
{
  "type": "AGENT_UPDATE",
  "session_id": "uuid",
  "agent_id": "Agent1",
  "agent_name": "Image Forensics",
  "message": "ðŸ”¬ Running Error Level Analysis across full imageâ€¦",
  "data": {
    "status": "running",
    "thinking": "ðŸ”¬ Running Error Level Analysis across full imageâ€¦"
  }
}
```

**Type values:** `CONNECTED` Â· `AGENT_UPDATE` Â· `AGENT_COMPLETE` Â· `PIPELINE_PAUSED` Â· `PIPELINE_COMPLETE` Â· `HITL_CHECKPOINT` Â· `ERROR`

For `AGENT_COMPLETE`, `data` also includes:
```json
{
  "status": "complete",
  "confidence": 0.87,
  "findings_count": 5,
  "error": null,
  "tool_error_rate": 0.0,
  "deep_analysis_pending": false
}
```

