"""
Report Renderer Module
=====================

Renders forensic reports in various formats (text, HTML, JSON).
"""

from typing import Any

from agents.arbiter import ForensicReport, render_text_report


def render_text(report: ForensicReport) -> str:
    """
    Render a forensic report as plain text/markdown.
    
    Args:
        report: The ForensicReport to render
        
    Returns:
        Formatted text report
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
        f"  <h1>Forensic Analysis Report</h1>",
        f"  <p><strong>Report ID:</strong> {report.report_id}</p>",
        f"  <p><strong>Case ID:</strong> {report.case_id}</p>",
        f"  <p><strong>Session ID:</strong> {report.session_id}</p>",
        f"  <p><strong>Signed:</strong> {report.signed_utc.isoformat() if report.signed_utc else 'N/A'}</p>",
        "",
        "  <div class='section'>",
        "    <h2>Executive Summary</h2>",
        f"    <p>{report.executive_summary}</p>",
        "  </div>",
    ]
    
    # Per-agent findings
    html_parts.append("  <div class='section'>")
    html_parts.append("    <h2>Per-Agent Findings</h2>")
    for agent_id, findings in report.per_agent_findings.items():
        html_parts.append(f"    <h3>{agent_id}</h3>")
        for finding in findings:
            html_parts.append(f"    <div class='finding'>{finding.get('finding_type', 'Unknown')}</div>")
    html_parts.append("  </div>")
    
    # Cross-modal confirmed
    if report.cross_modal_confirmed:
        html_parts.append("  <div class='section'>")
        html_parts.append("    <h2>Cross-Modal Confirmed Findings</h2>")
        for finding in report.cross_modal_confirmed:
            html_parts.append(f"    <div class='finding'>{finding.get('finding_type', 'Unknown')}</div>")
        html_parts.append("  </div>")
    
    # Uncertainty statement
    html_parts.append("  <div class='section'>")
    html_parts.append("    <h2>Uncertainty Statement</h2>")
    html_parts.append(f"    <p>{report.uncertainty_statement}</p>")
    html_parts.append("  </div>")
    
    # Cryptographic signature
    html_parts.append("  <div class='section'>")
    html_parts.append("    <h2>Cryptographic Signature</h2>")
    html_parts.append(f"    <p><strong>Report Hash:</strong> {report.report_hash}</p>")
    html_parts.append(f"    <p class='signature'><strong>Signature:</strong> {report.cryptographic_signature[:64]}...</p>")
    html_parts.append("  </div>")
    
    html_parts.extend([
        "</body>",
        "</html>",
    ])
    
    return "\n".join(html_parts)


def render_json(report: ForensicReport) -> dict[str, Any]:
    """
    Render a forensic report as JSON-serializable dict.
    
    Args:
        report: The ForensicReport to render
        
    Returns:
        Dictionary representation of the report
    """
    return report.model_dump(mode='json')
