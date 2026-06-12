# Calibration Runbook — Agents 2 / 3 / 4

**Date:** 2026-06-12
**Status:** Agent5 (text) is **TRAINED + ADOPTED** (HC3, see `storage/calibration_models/Agent5/`). Agent1 (image) calibration is wired and runnable. **Agents 2, 3, 4 remain UNCALIBRATED** — this runbook is how to take each to TRAINED once its labelled benchmark is on disk. Until then every confidence they contribute is disclosed as *"indicative (uncalibrated)"* in the signed report (Phase 0.7 / 3.3).

The detectors, collector, ROC sweep, validation gate, and a single end-to-end runner are all in place. What is **not** in the repo (by design — large + EULA-gated) is the benchmark media. The only manual step is staging that media into `--real` / `--fake` directories.

---

## One-command runner

Run from `apps/api` (the detectors import the app package):

```bash
python scripts/run_agent_calibration.py --agent AgentN \
    --real /path/to/authentic --fake /path/to/manipulated [--adopt]
```

It chains: **collect** (`collect_calibration_scores.py`) → **sweep** (`run_threshold_sweep.py`, Phase 1b ROC + operating thresholds) → **validate** (`validate_calibration.py`, held-out ADOPT/KEEP_DEFAULT gate) → **train+persist** (`train_calibration.py`, *only* with `--adopt` **and** an ADOPT verdict).

Nothing is swapped into the live store unless the gate says ADOPT **and** you pass `--adopt`. Drop `--adopt` for a dry run that produces the CSV + sweep JSON and prints the verdict without touching the model.

> **Key convention:** `--agent` is the **capitalised store key** (`Agent1`…`Agent5`) — that is the directory the running system loads (`storage/calibration_models/AgentN/`). The collector picks its runner by `--detector` (modality default shown per agent below); the runner fills it in for you.

CPU note: detector inference is the only slow step (minutes for audio/video clips, longer for image sets). Run overnight via the worker container where the ML stack is resident. A few hundred samples per class is enough for a stable 2-parameter Platt fit.

---

## Agent 2 — Audio (synthetic / cloned voice)

| | |
|---|---|
| Detector | `voice_clone` → `clone_probability` |
| Benchmark | **ASVspoof 2021 DF** (the codec-processed split — it matches deployment). Also usable: WaveFake, In-the-Wild. |
| Source | ASVspoof: https://www.asvspoof.org/ (DF eval set). Non-EULA alternative: `load_dataset("mteb/...")` style HF slices, or the In-the-Wild deepfake-audio set. |
| EULA | ASVspoof requires accepting its license; no individual approval queue. |
| Target | ~500 bona-fide (label 0) + ~500 spoof (label 1). |

```bash
python scripts/run_agent_calibration.py --agent Agent2 \
    --real /data/asvspoof21_df/bonafide --fake /data/asvspoof21_df/spoof --adopt
```

## Agent 3 — Image splicing (TruFor)

| | |
|---|---|
| Detector | `splicing` → TruFor `detection_score` |
| Benchmark | **CASIA v2** (authentic vs spliced/tampered). Also: Columbia, IMD2020, DEFACTO. |
| Source | CASIA v2 mirrors on HuggingFace / Kaggle (e.g. `load_dataset` slices). |
| EULA | None for CASIA v2 (research-open). |
| Target | ~1,000 authentic + ~1,000 spliced. |
| Note | `ENABLE_RESEARCH_MODELS=true` must be set so the **real TruFor** path runs — calibration is config-specific. Record `research_models: on` with the model. Rows are auto-skipped if TruFor weights are absent (the collector returns `None`). |

```bash
ENABLE_RESEARCH_MODELS=true python scripts/run_agent_calibration.py --agent Agent3 \
    --real /data/casia2/authentic --fake /data/casia2/spliced --adopt
```

## Agent 4 — Video (temporal deepfake)

| | |
|---|---|
| Detector | `deepfake_video` → `interframe_probability` |
| Benchmark | **FaceForensics++**, **DFDC**, or **Celeb-DF v2**. |
| Source | FF++: https://github.com/ondyari/FaceForensics ; DFDC: Kaggle. |
| EULA | **Gated** — FF++ and DFDC both require a signed request/approval. Apply now; calibrate when granted. |
| Target | ~500 real + ~500 fake clips (sampled frames scored per clip). |
| Note | Until access is granted, Agent4 confidence stays labelled uncalibrated — that is the honest default, already wired. |

```bash
python scripts/run_agent_calibration.py --agent Agent4 \
    --real /data/ffpp/real --fake /data/ffpp/fake --adopt
```

---

## After adoption

1. Confirm the model landed: `storage/calibration_models/AgentN/latest.json` has `"calibration_status": "TRAINED"` and a `benchmark_dataset` string.
2. The report's **Reliability Notes** will now carry the positive calibration disclosure for that agent (Phase 3.3), citing the dataset + model version, and its confidences drop the *"indicative (uncalibrated)"* label.
3. The Phase 1b sweep JSON (`calibration_data/agentN_<detector>_sweep.json`) holds the per-tool `(threshold, TPR, FPR)` operating points — fold the chosen point into the capability manifest so reports disclose measured per-tool error rates.

See `docs/CALIBRATION.md` for the calibration workflow + golden rule and the dataset-acquisition helper (`acquire_calibration_datasets.sh`); `docs/CHANGELOG.md` (v1.9.0) records the completed elevation/calibration work and rationale.
