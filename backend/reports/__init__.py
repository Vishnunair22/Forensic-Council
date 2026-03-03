"""
Forensic Council Reports Module
=============================

Renders forensic reports in various formats.
"""

from reports.report_renderer import render_text, render_html, render_json

__all__ = [
    "render_text",
    "render_html", 
    "render_json",
]
