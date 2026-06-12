#!/usr/bin/env python3
"""End-to-end per-agent calibration runner (see docs/CALIBRATION_RUNBOOK.md).

One command takes a LABELLED benchmark for ONE agent through the full pipeline:

    collect_calibration_scores.py   (detector → score,label CSV)
      → run_threshold_sweep.py      (ROC table + operating thresholds — Phase 1b)
      → validate_calibration.py     (held-out ADOPT / KEEP_DEFAULT gate)
      → train_calibration.py        (persist the model — ONLY with --adopt AND an
                                      ADOPT verdict)

Nothing is adopted unless the gate returns ADOPT *and* ``--adopt`` is supplied,
so a confidence model is never silently swapped in on weak data (the plan's
"adopt on ADOPT verdict only" rule).

Agent → detector → store-key convention. The calibration store dir / runtime key
is the CAPITALISED ``AgentN`` (that is the key the running system loads — see the
adopted Agent5 model under ``storage/calibration_models/Agent5``). The collector
selects its runner by ``--detector`` name, not the agent key:

    Agent1   ai_generation    AI-generated image probability
    Agent2   voice_clone      synthetic / cloned voice probability
    Agent3   splicing         TruFor detection_score (region tampering)
    Agent4   deepfake_video   inter-frame temporal-forgery probability
    Agent5   ai_text          AI-authored text probability

Run from ``apps/api`` (the detectors import the app package):

    python scripts/run_agent_calibration.py --agent Agent3 \
        --real /data/casia/authentic --fake /data/casia/spliced
    # add --adopt to persist into storage/calibration_models/ when ADOPT

Exit codes: 0 success (ADOPT, or collected+validated without --adopt),
2 KEEP_DEFAULT / insufficient data, 1 hard error.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Agent store-key → default detector for that modality.
AGENT_DETECTORS: dict[str, str] = {
    "Agent1": "ai_generation",
    "Agent2": "voice_clone",
    "Agent3": "splicing",
    "Agent4": "deepfake_video",
    "Agent5": "ai_text",
}

_SCRIPTS = Path(__file__).resolve().parent


def _run(label: str, argv: list[str]) -> tuple[int, str]:
    """Run a child script, streaming nothing but capturing combined output."""
    print(f"\n=== {label} ===")
    print("  $ " + " ".join(argv))
    proc = subprocess.run(argv, capture_output=True, text=True)  # noqa: S603 — fixed interpreter + repo scripts, not user input
    out = (proc.stdout or "") + (proc.stderr or "")
    print(out.rstrip())
    return proc.returncode, out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agent", required=True, choices=sorted(AGENT_DETECTORS), help="Store key, e.g. Agent3")
    ap.add_argument("--detector", default=None, help="Override the modality default detector")
    ap.add_argument("--real", help="Directory of authentic samples (label 0)")
    ap.add_argument("--fake", help="Directory of manipulated/AI samples (label 1)")
    ap.add_argument("--labels", help="CSV manifest with columns: path,label")
    ap.add_argument("--out-dir", default="calibration_data", help="Where to write the CSV + sweep JSON")
    ap.add_argument("--adopt", action="store_true", help="Persist the model when the gate verdict is ADOPT")
    ap.add_argument("--test-frac", type=float, default=0.3, help="Held-out fraction for the validation gate")
    args = ap.parse_args()

    if not args.labels and not (args.real or args.fake):
        print("ERROR: provide --labels OR --real/--fake", file=sys.stderr)
        return 1

    detector = args.detector or AGENT_DETECTORS[args.agent]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{args.agent.lower()}_{detector}"
    csv_path = out_dir / f"{stem}.csv"
    sweep_path = out_dir / f"{stem}_sweep.json"

    py = sys.executable

    # 1) Collect scores -----------------------------------------------------
    collect = [py, str(_SCRIPTS / "collect_calibration_scores.py"),
               "--detector", detector, "--out", str(csv_path)]
    if args.labels:
        collect += ["--labels", args.labels]
    else:
        if args.real:
            collect += ["--real", args.real]
        if args.fake:
            collect += ["--fake", args.fake]
    rc, _ = _run("1/4 collect scores", collect)
    if rc not in (0,) or not csv_path.exists():
        print(f"\nFAILED at collection (rc={rc}). No CSV produced — check the detector/data.", file=sys.stderr)
        return 1

    # 2) Threshold sweep (Phase 1b) ----------------------------------------
    _run("2/4 threshold sweep", [
        py, str(_SCRIPTS / "run_threshold_sweep.py"),
        "--csv", str(csv_path), "--detector", detector, "--out", str(sweep_path),
    ])

    # 3) Validation gate ----------------------------------------------------
    rc, vout = _run("3/4 validation gate", [
        py, str(_SCRIPTS / "validate_calibration.py"),
        "--dataset", str(csv_path), "--agent", args.agent,
        "--test-frac", str(args.test_frac),
    ])
    adopt_verdict = "VERDICT: ADOPT" in vout

    # 4) Train + persist — only on ADOPT and explicit --adopt ---------------
    if adopt_verdict and args.adopt:
        rc_t, _ = _run("4/4 train + persist", [
            py, str(_SCRIPTS / "train_calibration.py"),
            "--dataset", str(csv_path), "--agent", args.agent,
            "--output-dir", "storage/calibration_models",
        ])
        if rc_t != 0:
            print(f"\nADOPT verdict but persistence failed (rc={rc_t}).", file=sys.stderr)
            return 1
        print(f"\nDONE: {args.agent} calibrated and ADOPTED. CSV={csv_path} sweep={sweep_path}")
        return 0

    if adopt_verdict:
        print(
            f"\nDONE: gate says ADOPT for {args.agent}, but --adopt was not passed — "
            f"nothing persisted. Re-run with --adopt to swap the model in.\n"
            f"  CSV={csv_path}  sweep={sweep_path}"
        )
        return 0

    print(
        f"\nDONE: gate did NOT adopt {args.agent} (KEEP_DEFAULT / insufficient data). "
        f"Confidence stays uncalibrated and is disclosed as such in reports.\n"
        f"  CSV={csv_path}  sweep={sweep_path}"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
