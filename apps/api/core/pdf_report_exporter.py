"""
PDF Report Exporter
====================

Generates court-ready PDF forensic reports from ForensicReport objects.

Implements a two-tier approach:
  Tier 1 (primary): HTML-to-PDF via WeasyPrint (if installed)
  Tier 2 (fallback): Pure-Python reportlab-style text PDF via fpdf2 (if installed)
  Tier 3 (always available): Structured HTML report written to disk (no PDF deps needed)

Usage:
    from core.pdf_report_exporter import export_report_pdf

    pdf_bytes = await export_report_pdf(report, session_id)
    # Returns bytes — write to file or return as HTTP response
"""

from __future__ import annotations

import html
import textwrap
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.structured_logging import get_logger

logger = get_logger(__name__)


def _normalize_report_for_template(report_dict: dict[str, Any]) -> dict[str, Any]:
    """Map DTO field names to template-friendly view-model keys."""
    return {
        "verdict": report_dict.get("overall_verdict", "INCONCLUSIVE"),
        "confidence": report_dict.get("overall_confidence", report_dict.get("confidence", 0.0)),
        "case_id": report_dict.get("case_id", "UNKNOWN"),
        "narrative": report_dict.get("executive_summary", report_dict.get("narrative", report_dict.get("summary", "No narrative generated."))),
        "agents": report_dict.get("per_agent_metrics", report_dict.get("agent_metrics", report_dict.get("agents", {}))),
        "findings": report_dict.get("per_agent_findings", report_dict.get("findings", [])),
        "created": report_dict.get("signed_utc", report_dict.get("created_utc", datetime.now(UTC).isoformat())),
        "report_hash": report_dict.get("report_hash", "N/A"),
        "manipulation_probability": report_dict.get("manipulation_probability", report_dict.get("overall_confidence", 0.0)),
        "calibrated": report_dict.get("calibrated", False),
        "session_id": report_dict.get("session_id", ""),
    }


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

_REPORT_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Forensic Council — {session_id}</title>
<style>
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 10pt;
          color: #1a1a2e; margin: 0; padding: 0; }}
  .cover {{ background: #1a1a2e; color: #e0e0ff; padding: 48pt 36pt 36pt;
             page-break-after: always; }}
  .cover h1 {{ font-size: 22pt; margin: 0 0 4pt; letter-spacing: 1px; }}
  .cover .sub {{ font-size: 10pt; color: #9090cc; margin-bottom: 24pt; }}
  .cover .meta {{ font-size: 9pt; color: #c0c0e0; line-height: 1.8; }}
  .cover .verdict-box {{ margin-top: 28pt; padding: 16pt; border-radius: 6pt;
    background: {verdict_bg}; }}
  .cover .verdict-label {{ font-size: 8pt; text-transform: uppercase;
    letter-spacing: 2px; color: #a0a0cc; }}
  .cover .verdict-text {{ font-size: 18pt; font-weight: bold; color: {verdict_color}; }}
  .cover .confidence {{ font-size: 11pt; color: #c0c0e0; }}
  .section {{ padding: 24pt 36pt; border-bottom: 1pt solid #e0e0f0; }}
  .section h2 {{ font-size: 13pt; color: #1a1a2e; border-bottom: 2pt solid #4040aa;
                 padding-bottom: 4pt; margin-bottom: 12pt; }}
  .section h3 {{ font-size: 10pt; color: #2a2a5e; margin: 10pt 0 4pt; }}
  .finding {{ background: #f8f8ff; border-left: 3pt solid {finding_color};
              padding: 8pt 12pt; margin: 6pt 0; border-radius: 0 4pt 4pt 0; }}
  .finding .ftype {{ font-size: 8pt; text-transform: uppercase; color: #6060aa;
                     letter-spacing: 1px; }}
  .finding .fsummary {{ font-size: 9pt; margin-top: 4pt; color: #333; }}
  .finding .fconf {{ font-size: 8pt; color: #666; margin-top: 3pt; }}
  .uncal-badge {{ display: inline-block; background: #ff990044; color: #cc6600;
                  font-size: 7pt; padding: 1pt 5pt; border-radius: 3pt;
                  border: 1pt solid #cc660033; margin-left: 4pt; }}
  .agent-section {{ margin: 8pt 0; }}
  .agent-header {{ background: #f0f0ff; padding: 6pt 12pt; border-radius: 4pt;
                   font-weight: bold; font-size: 9pt; color: #2a2a6e; }}
  .narrative {{ font-size: 9.5pt; line-height: 1.6; color: #222; white-space: pre-wrap;
                word-break: break-word; overflow-wrap: anywhere;
                background: #fafafa; border: 1pt solid #e0e0f0; border-radius: 4pt;
                padding: 12pt; }}
  .custody-table {{ width: 100%; border-collapse: collapse; font-size: 8pt; margin-top: 8pt; }}
  .custody-table th {{ background: #1a1a2e; color: #e0e0ff; padding: 4pt 8pt;
                       text-align: left; }}
  .custody-table td {{ padding: 4pt 8pt; border-bottom: 1pt solid #e8e8f0; color: #333; }}
  .hash-box {{ font-family: monospace; font-size: 8pt; color: #444; background: #f0f0f8;
               padding: 6pt 10pt; border-radius: 3pt; word-break: break-all; }}
  .footer {{ padding: 12pt 36pt; background: #f0f0f8; font-size: 8pt; color: #888;
             text-align: center; }}
  @page {{ margin: 36pt; @bottom-center {{ content: "Forensic Council — CONFIDENTIAL — Page " counter(page) " of " counter(pages); font-size: 8pt; color: #888; }} }}
</style>
</head>
<body>
{body}
<div class="footer">
  FORENSIC COUNCIL — CONFIDENTIAL FORENSIC REPORT<br>
  Generated: {generated_at} | Session: {session_id}<br>
  This report is generated by an automated multi-agent forensic system.
  All findings should be reviewed by a qualified forensic analyst before use in legal proceedings.
</div>
</body>
</html>"""


def _verdict_colors(verdict: str) -> tuple[str, str, str]:
    """Return (bg_color, text_color, finding_border_color) for a verdict string."""
    v = (verdict or "").upper()
    if v in ("TAMPERED", "MANIPULATED", "HIGH"):
        return "#3d0000", "#ff6060", "#cc2222"
    elif v in ("SUSPICIOUS", "MEDIUM", "PARTIALLY_CORROBORATED"):
        return "#3d2200", "#ffaa44", "#cc7700"
    elif v in ("AUTHENTIC", "CLEAN", "LOW", "LIKELY_AUTHENTIC"):
        return "#003d00", "#66ff88", "#22aa44"
    else:
        return "#1a1a3e", "#9090cc", "#4444aa"


def _build_html_body(report_dict: dict[str, Any], session_id: str) -> str:
    """Build the HTML body from a ForensicReport dict, using normalized template fields."""
    tmpl = _normalize_report_for_template(report_dict)

    def esc(v: Any) -> str:
        return html.escape(str(v))

    verdict = esc(tmpl["verdict"])
    tmpl["confidence"]
    case_id = esc(tmpl["case_id"])
    narrative = esc(tmpl["narrative"])
    agents = tmpl["agents"]
    findings_raw = tmpl["findings"]
    created = esc(tmpl["created"])
    report_hash = esc(tmpl["report_hash"])
    manipulation_probability = tmpl["manipulation_probability"]

    verdict_bg, verdict_color, finding_color = _verdict_colors(verdict)

    # Cover page
    sections = [f"""<div class="cover">
  <h1>FORENSIC COUNCIL</h1>
  <div class="sub">Multi-Agent Forensic Evidence Analysis Report</div>
  <div class="meta">
    Case ID: {case_id}<br>
    Session: {esc(session_id)}<br>
    Generated: {created}
  </div>
  <div class="verdict-box">
    <div class="verdict-label">Final Verdict</div>
    <div class="verdict-text">{verdict}</div>
    <div class="confidence">Manipulation Probability: {float(manipulation_probability):.1%}</div>
  </div>
</div>"""]

    # Narrative section
    sections.append(f"""<div class="section">
  <h2>Investigation Narrative</h2>
  <div class="narrative">{narrative}</div>
</div>""")

    # Agent findings section
    findings_list: list[dict] = []
    if isinstance(findings_raw, dict):
        for agent_findings in findings_raw.values():
            if isinstance(agent_findings, list):
                findings_list.extend(agent_findings)
    elif isinstance(findings_raw, list):
        findings_list = findings_raw

    if findings_list or agents:
        agent_html_parts = []

        by_agent: dict[str, list[dict]] = {}
        for f in findings_list:
            aid = esc(f.get("agent_id", "Unknown")) if isinstance(f, dict) else "Unknown"
            by_agent.setdefault(aid, []).append(f)

        for agent_id, agent_findings in sorted(by_agent.items()):
            finding_items = []
            for f in agent_findings:
                if not isinstance(f, dict):
                    continue
                ftype = esc(f.get("finding_type", "Unknown"))
                fsummary = esc(f.get("reasoning_summary", "")[:300])
                fconf = f.get("confidence_raw") or f.get("raw_confidence_score")
                cal_status = f.get("calibration_status", "UNCALIBRATED")
                everd = esc(f.get("evidence_verdict", "INCONCLUSIVE"))

                cal_badge = ""
                if cal_status == "UNCALIBRATED":
                    cal_badge = '<span class="uncal-badge">UNCALIBRATED</span>'

                conf_str = f"{float(fconf):.1%}" if fconf is not None else "N/A"
                finding_items.append(f"""<div class="finding">
  <div class="ftype">{ftype}{cal_badge}</div>
  <div class="fsummary">{fsummary}</div>
  <div class="fconf">Verdict: {everd} | Confidence: {conf_str} | Status: {esc(f.get('status', ''))}</div>
</div>""")

            agent_html_parts.append(f"""<div class="agent-section">
  <div class="agent-header">{esc(agent_id)}</div>
  {"".join(finding_items) if finding_items else '<p style="color:#888;font-size:9pt;">No findings recorded.</p>'}
</div>""")

        sections.append(f"""<div class="section">
  <h2>Agent Findings</h2>
  {"".join(agent_html_parts)}
</div>""")

    # Chain of custody / integrity section
    sections.append(f"""<div class="section">
  <h2>Integrity & Chain of Custody</h2>
  <h3>Report Hash (SHA-256)</h3>
  <div class="hash-box">{report_hash}</div>
  <h3>Custody Metadata</h3>
  <table class="custody-table">
    <tr><th>Field</th><th>Value</th></tr>
    <tr><td>Session ID</td><td>{esc(session_id)}</td></tr>
    <tr><td>Case ID</td><td>{case_id}</td></tr>
    <tr><td>Report Generated</td><td>{created}</td></tr>
    <tr><td>Verdict</td><td>{verdict}</td></tr>
    <tr><td>Manipulation Probability</td><td>{float(manipulation_probability):.1%}</td></tr>
    <tr><td>Calibration Status</td><td>{'TRAINED' if tmpl.get('calibrated') else 'UNCALIBRATED'}</td></tr>
  </table>
  <p style="font-size:8pt;color:#888;margin-top:8pt;">
    UNCALIBRATED means confidence scores are engineering defaults, not trained on labelled forensic data.
    These scores should not be relied upon as calibrated probabilities in legal proceedings.
  </p>
</div>""")

    return "\n".join(sections)


async def export_report_html(
    report_dict: dict[str, Any],
    session_id: str,
) -> str:
    """Export a ForensicReport as an HTML string."""
    body = _build_html_body(report_dict, session_id)
    generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    html = _REPORT_HTML_TEMPLATE.format(
        session_id=session_id,
        body=body,
        generated_at=generated_at,
        verdict_bg=_verdict_colors(report_dict.get("verdict", ""))[0],
        verdict_color=_verdict_colors(report_dict.get("verdict", ""))[1],
        finding_color=_verdict_colors(report_dict.get("verdict", ""))[2],
    )
    return html


async def export_report_pdf(
    report_dict: dict[str, Any],
    session_id: str,
    output_path: Path | None = None,
) -> bytes | None:
    """
    Export a ForensicReport as PDF bytes.

    Tries WeasyPrint first, falls back to fpdf2, falls back to HTML file.

    Args:
        report_dict: Serialized ForensicReport as dict
        session_id: Session identifier for naming
        output_path: Optional path to write the file (in addition to returning bytes)

    Returns:
        PDF bytes if a PDF library is available, None otherwise.
        HTML file is always written to reports/ directory.
    """
    html = await export_report_html(report_dict, session_id)

    # --- Try WeasyPrint ---
    try:
        from weasyprint import HTML as WEASY_HTML  # type: ignore[import]

        pdf_bytes = WEASY_HTML(string=html).write_pdf()
        if output_path:
            output_path.write_bytes(pdf_bytes)
        logger.info("PDF report generated via WeasyPrint", session_id=session_id)
        return pdf_bytes
    except ImportError:
        logger.debug("WeasyPrint not installed — trying fpdf2")
    except Exception as e:
        logger.warning("WeasyPrint PDF generation failed", error=str(e))

    # --- Try fpdf2 ---
    try:
        from fpdf import FPDF  # type: ignore[import]  # noqa: F401 — used via _build_text_pdf_fpdf2

        report = _build_text_pdf_fpdf2(report_dict, session_id)
        pdf_bytes = bytes(report.output())
        if output_path:
            output_path.write_bytes(pdf_bytes)
        logger.info("PDF report generated via fpdf2", session_id=session_id)
        return pdf_bytes
    except ImportError:
        logger.warning(
            "No PDF library available (WeasyPrint or fpdf2). "
            "HTML report written to reports/ directory. "
            "Install WeasyPrint: pip install weasyprint"
        )
    except Exception as e:
        logger.warning("fpdf2 PDF generation failed", error=str(e))

    return None


def _safe_latin1(text: str) -> str:
    """Normalize unicode to Latin-1 safe string for fpdf2 built-in fonts."""
    return (
        text.replace("—", "--")  # em dash
            .replace("–", "-")   # en dash
            .replace("‘", "'").replace("’", "'")  # curly single quotes
            .replace("“", '"').replace("”", '"')  # curly double quotes
            .replace("…", "...")  # ellipsis
            .encode("latin-1", errors="replace").decode("latin-1")
    )


def _build_text_pdf_fpdf2(report_dict: dict[str, Any], session_id: str) -> Any:
    """Build a simple text-based PDF using fpdf2."""
    from fpdf import FPDF  # type: ignore[import]

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Title
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "FORENSIC COUNCIL -- CONFIDENTIAL REPORT", align="C")
    pdf.ln(10)
    pdf.ln(4)

    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6, f"Session: {session_id}")
    pdf.ln(6)
    pdf.cell(0, 6, f"Case: {report_dict.get('case_id', 'N/A')}")
    pdf.ln(6)
    pdf.cell(0, 6, f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    pdf.ln(6)
    pdf.ln(6)

    # Verdict
    pdf.set_font("Helvetica", "B", 12)
    verdict = report_dict.get("overall_verdict", report_dict.get("verdict", "INCONCLUSIVE"))
    prob = float(report_dict.get("manipulation_probability", 0.0))
    pdf.cell(0, 8, f"VERDICT: {verdict}  |  Manipulation Probability: {prob:.1%}")
    pdf.ln(8)
    pdf.ln(4)

    # Executive summary
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Executive Summary")
    pdf.ln(7)
    pdf.set_font("Helvetica", "", 9)
    narrative = str(report_dict.get("executive_summary", report_dict.get("narrative", report_dict.get("summary", "No summary."))))
    for line in textwrap.wrap(_safe_latin1(narrative), width=90):
        pdf.cell(0, 5, line)
        pdf.ln(5)
    pdf.ln(4)

    # Verdict sentence
    vs = report_dict.get("verdict_sentence", "")
    if vs:
        pdf.set_font("Helvetica", "I", 9)
        for line in textwrap.wrap(_safe_latin1(str(vs)), width=90):
            pdf.cell(0, 5, line)
            pdf.ln(5)
        pdf.ln(2)

    # Findings summary
    all_findings = []
    per_agent = report_dict.get("per_agent_findings", {})
    if isinstance(per_agent, dict):
        for agent_findings in per_agent.values():
            if isinstance(agent_findings, list):
                all_findings.extend(agent_findings)
    findings = all_findings or report_dict.get("findings", [])
    if findings:
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, f"Findings ({len(findings)} total)")
        pdf.ln(7)
        pdf.set_font("Helvetica", "", 8)
        for f in findings[:20]:  # Cap at 20 to avoid overflow
            if not isinstance(f, dict):
                continue
            ftype = _safe_latin1(f.get("finding_type", "Unknown")[:60])
            fconf = f.get("confidence_raw")
            conf_str = f"{float(fconf):.0%}" if fconf is not None else "N/A"
            everd = f.get("evidence_verdict", "?")[:20]
            pdf.cell(0, 5, f"  [{everd}] {ftype} - Conf: {conf_str}")
            pdf.ln(5)

    # Hash
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 6, "Report Integrity (SHA-256):")
    pdf.ln(6)
    pdf.set_font("Courier", "", 8)
    pdf.cell(0, 5, report_dict.get("report_hash", "N/A")[:80])
    pdf.ln(5)

    return pdf


def probe_pdf_libs() -> dict[str, bool]:
    """Probe availability of PDF generation libraries at startup."""
    result: dict[str, bool] = {}
    try:
        import weasyprint  # noqa: F401
        result["weasyprint"] = True
    except ImportError:
        result["weasyprint"] = False
    try:
        from fpdf import FPDF  # noqa: F401
        result["fpdf2"] = True
    except ImportError:
        result["fpdf2"] = False
    return result
