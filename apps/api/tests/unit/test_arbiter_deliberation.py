"""Regression tests for arbiter finding partitioning.

Guards against tool findings being silently dropped during deliberation: every
report-safe finding must surface in either strongest_findings or
supporting_findings, and only non-report-safe findings may be excluded.
"""

from core.arbiter_deliberation import deliberate_findings


def _finding(tool: str, *, fid: str, verdict: str = "NEGATIVE", agent_id: str = "Agent1") -> dict:
    return {
        "finding_id": fid,
        "agent_id": agent_id,
        "evidence_verdict": verdict,
        "status": "COMPLETE",
        "reasoning_summary": f"{tool} ran and reported {verdict}.",
        "metadata": {"tool_name": tool, "court_defensible": True},
    }


def _deliberate(findings):
    return deliberate_findings(
        findings,
        visual_context=None,
        tool_coverage={"completed_tools": [], "failed_tools": []},
        mime_type="image/jpeg",
    )


def test_low_weight_report_safe_finding_is_not_dropped():
    # copy_move_detect is weighted LOW. Before the fix, a report-safe LOW finding
    # landed in NO output bucket (strongest=CRITICAL/HIGH, supporting=MEDIUM only,
    # excluded=not-report-safe) and vanished from the report.
    result = _deliberate([_finding("copy_move_detect", fid="low1")])

    surfaced = {
        f.finding_id
        for f in result.strongest_findings + result.supporting_findings + result.excluded_findings
    }
    assert "low1" in surfaced
    # It is report-safe, so it must appear as supporting evidence (not excluded).
    assert any(f.finding_id == "low1" for f in result.supporting_findings)
    assert all(f.finding_id != "low1" for f in result.excluded_findings)


def test_every_report_safe_finding_is_partitioned():
    findings = [
        _finding("ela_full_image", fid="crit"),       # CRITICAL → strongest
        _finding("brand_new_tool", fid="med"),         # default MEDIUM → supporting
        _finding("jpeg_ghost_detect", fid="low"),      # LOW → supporting
    ]
    result = _deliberate(findings)

    surfaced = {f.finding_id for f in result.strongest_findings + result.supporting_findings}
    assert {"crit", "med", "low"} <= surfaced
    # Clean/report-safe findings are never excluded.
    assert not result.excluded_findings


def test_non_report_safe_finding_is_excluded_not_supporting():
    bad = _finding("ela_full_image", fid="err", verdict="ERROR")
    result = _deliberate([bad])

    assert any(f.finding_id == "err" for f in result.excluded_findings)
    assert all(f.finding_id != "err" for f in result.strongest_findings + result.supporting_findings)
