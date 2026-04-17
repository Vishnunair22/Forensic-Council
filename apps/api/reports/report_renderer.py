"""
Report Renderer Module
=====================

Renders forensic reports in various formats (text, HTML, JSON).
"""

from html import escape as _esc
from typing import Any

from agents.arbiter_verdict import ForensicReport


def render_text_report(report: ForensicReport) -> str:
    """Render ForensicReport as structured plain text/markdown."""
    lines = []
    lines.append("=" * 80)
    lines.append("FORENSIC ANALYSIS REPORT")
    lines.append("=" * 80)
    lines.append(f"Report ID: {report.report_id}")
    lines.append(f"Session ID: {report.session_id}")
    lines.append(f"Case ID: {report.case_id}")
    if report.signed_utc:
        lines.append(f"Signed: {report.signed_utc.isoformat()}")
    lines.append("")

    lines.append("-" * 80)
    lines.append("EXECUTIVE SUMMARY")
    lines.append("-" * 80)
    lines.append(report.executive_summary)
    lines.append("")

    lines.append("-" * 80)
    lines.append("PER-AGENT FINDINGS")
    lines.append("-" * 80)
    for agent_id, findings in report.per_agent_findings.items():
        lines.append(f"### {agent_id}")
        for finding in findings:
            lines.append(
                f"  - {finding.get('finding_type', 'Unknown')}: {finding.get('confidence_raw', 0):.2f}"
            )
    lines.append("")

    if report.cross_modal_confirmed:
        lines.append("-" * 80)
        lines.append("CROSS-MODAL CONFIRMED FINDINGS")
        lines.append("-" * 80)
        for finding in report.cross_modal_confirmed:
            lines.append(f"  - {finding.get('finding_type', 'Unknown')}")
        lines.append("")

    lines.append("-" * 80)
    lines.append("UNCERTAINTY STATEMENT")
    lines.append("-" * 80)
    lines.append(report.uncertainty_statement)
    lines.append("")

    lines.append("-" * 80)
    lines.append("CRYPTOGRAPHIC SIGNATURE")
    lines.append("-" * 80)
    lines.append(f"Report Hash: {report.report_hash}")
    lines.append(f"Signature: {report.cryptographic_signature[:64]}...")
    lines.append("")
    lines.append("=" * 80)

    return "\n".join(lines)


def render_text(report: ForensicReport) -> str:
    """
    Render a forensic report as plain text/markdown.
    """
    return render_text_report(report)


def render_html(report: ForensicReport) -> str:
    """
    Render a forensic report as HTML.

    Args:
        report: The ForensicReport to render

    Returns:
        HTML-formatted report
    """
    html_parts = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        "  <meta charset='UTF-8'>",
        "  <title>Forensic Analysis Report</title>",
        "  <style>",
        "    body { font-family: Arial, sans-serif; margin: 40px; }",
        "    h1 { color: #333; }",
        "    h2 { color: #666; border-bottom: 1px solid #ccc; }",
        "    .section { margin: 20px 0; }",
        "    .finding { background: #f5f5f5; padding: 10px; margin: 5px 0; }",
        "    .signature { font-family: monospace; font-size: 12px; }",
        "  </style>",
        "</head>",
        "<body>",
        "  <h1>Forensic Analysis Report</h1>",
        f"  <p><strong>Report ID:</strong> {_esc(str(report.report_id))}</p>",
        f"  <p><strong>Case ID:</strong> {_esc(str(report.case_id))}</p>",
        f"  <p><strong>Session ID:</strong> {_esc(str(report.session_id))}</p>",
        f"  <p><strong>Signed:</strong> {_esc(report.signed_utc.isoformat() if report.signed_utc else 'N/A')}</p>",
        "",
        "  <div class='section'>",
        "    <h2>Executive Summary</h2>",
        f"    <p>{_esc(report.executive_summary or 'N/A')}</p>",
        "  </div>",
    ]

    # Per-agent findings
    html_parts.append("  <div class='section'>")
    html_parts.append("    <h2>Per-Agent Findings</h2>")
    for agent_id, findings in report.per_agent_findings.items():
        html_parts.append(f"    <h3>{_esc(str(agent_id))}</h3>")
        for finding in findings:
            html_parts.append(
                f"    <div class='finding'>{_esc(str(finding.get('finding_type', 'Unknown')))}</div>"
            )
    html_parts.append("  </div>")

    # Cross-modal confirmed
    if report.cross_modal_confirmed:
        html_parts.append("  <div class='section'>")
        html_parts.append("    <h2>Cross-Modal Confirmed Findings</h2>")
        for finding in report.cross_modal_confirmed:
            html_parts.append(
                f"    <div class='finding'>{_esc(str(finding.get('finding_type', 'Unknown')))}</div>"
            )
        html_parts.append("  </div>")

    # Uncertainty statement
    html_parts.append("  <div class='section'>")
    html_parts.append("    <h2>Uncertainty Statement</h2>")
    html_parts.append(f"    <p>{_esc(report.uncertainty_statement or 'N/A')}</p>")
    html_parts.append("  </div>")

    # Cryptographic signature
    html_parts.append("  <div class='section'>")
    html_parts.append("    <h2>Cryptographic Signature</h2>")
    html_parts.append(
        f"    <p><strong>Report Hash:</strong> {_esc(report.report_hash)}</p>"
    )
    html_parts.append(
        f"    <p class='signature'><strong>Signature:</strong> {_esc((report.cryptographic_signature or '')[:64])}...</p>"
    )
    html_parts.append("  </div>")

    html_parts.extend(
        [
            "</body>",
            "</html>",
        ]
    )

    return "\n".join(html_parts)


def render_json(report: ForensicReport) -> dict[str, Any]:
    """
    Render a forensic report as JSON-serializable dict.

    Args:
        report: The ForensicReport to render

    Returns:
        Dictionary representation of the report
    """
    return report.model_dump(mode="json")
