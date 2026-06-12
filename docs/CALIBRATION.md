# Model Calibration — Datasets & Workflow

The Forensic Council ships **conservative engineering-default** Platt parameters
(`CalibrationStatus.UNCALIBRATED`). This guide is how to *refine* them with real,
current, ground-truth data so confidence numbers are honest (a "70%" means ~70%)
and thresholds are principled — **without ever degrading the system**.

> This is **calibration**, not model retraining. We fit a per-agent sigmoid that
> rescales raw detector scores. We do **not** retrain the underlying detectors —
> that needs GPUs, large curated corpora, and re-opens licensing. Where a model is
> genuinely *blind* (e.g. a synthesis method it cannot see), calibration cannot
> help; swap in a stronger detector instead.

## The golden rule: never adopt blind

A model fit on too-small or distribution-mismatched data is **worse** than the
default. Always go through the **adopt-only-if-it-beats-default** gate
(`validate_calibration.py`) — it adopts a trained model only if it improves
**ECE and Brier** on a held-out split **without raising the false-positive rate**.

## Current state

Agents ship `CalibrationStatus.UNCALIBRATED` engineering defaults. **Agent5 (text)
is TRAINED+ADOPTED** on HC3 (`storage/calibration_models/Agent5/`); Agent1 (image)
is wired and runnable; Agents 2/3/4 await their benchmark media. Uncalibrated
agents are disclosed as *"indicative (uncalibrated)"* in every signed report;
TRAINED agents cite their dataset + model version.

## Workflow

The fastest path is the one-command runner, which chains collect → threshold
sweep → validate → gated-train and persists **only** on an `ADOPT` verdict *and*
explicit `--adopt`:

```bash
python scripts/run_agent_calibration.py --agent Agent1 \
    --real /data/genimage/real --fake /data/genimage/ai --adopt
```

> `--agent` is the **capitalised store key** (`Agent1`…`Agent5`) — the directory the
> running system loads (`storage/calibration_models/AgentN/`). The runner selects
> the detector by modality; per-agent datasets + commands are in
> [CALIBRATION_RUNBOOK.md](CALIBRATION_RUNBOOK.md).

The same pipeline, run step by step:

```bash
# 1. Collect raw detector scores over a LABELLED benchmark (label 0=authentic, 1=manipulated/AI)
python scripts/collect_calibration_scores.py \
    --detector ai_generation \
    --real /data/genimage/real --fake /data/genimage/ai \
    --out /tmp/agent1_ai_scores.csv

# 2. Validate against the conservative default on a held-out split (the safety gate)
python scripts/validate_calibration.py --dataset /tmp/agent1_ai_scores.csv --agent Agent1
#   → VERDICT: ADOPT   (trained beats default on ECE+Brier, FPR not worse)
#   → VERDICT: KEEP_DEFAULT  (otherwise — do not persist)

# 3. Persist ONLY if step 2 said ADOPT
python scripts/train_calibration.py --dataset /tmp/agent1_ai_scores.csv \
    --agent Agent1 --output-dir storage/calibration_models
```

Run inside the worker container (ML models present). Calibrate **per agent /
per detector** — each needs data matching what it detects and the deployment
distribution.

## Current, authoritative benchmarks (use these, not random uploads)

Pick datasets with **known provenance and licensing** — the calibration set becomes
part of the methodology you would defend in court. Random "deepfake.zip" Kaggle
uploads with dubious labels calibrate to noise.

| Modality / detector | Agent | Recommended current benchmarks | Notes / licence |
| --- | --- | --- | --- |
| AI-generated images (`ai_generation`) | agent1_image | **GenImage** (2023), Synthbuster, DRCT-2M; real side: COCO/ImageNet subsets | research licences; balance generators (SD, Midjourney, DALL·E) |
| Image splicing / tamper (`splicing`) | agent1_image / agent3 | **NIST MFC 2018/2019**, CASIA v2, Columbia, DEFACTO (2019) | NIST requires registration; cite version |
| Audio spoof / synthetic voice (`voice_clone`) | agent2_audio | **ASVspoof 2019 LA + 2021 DF** (current TTS/VC) | ASVspoof EULA; 2021 DF covers modern neural TTS |
| Video / face deepfake | agent4_video | **FaceForensics++** (c23/c40), **DFDC**, Celeb-DF v2, DeepfakeTIMIT | large; sample a balanced subset; FF++/DFDC are EULA-gated |
| AI-generated text (`ai_text`) | agent5_metadata | **HC3** (used; TRAINED), RAID (2024), M4 | local `ai_text_detector.py` (statistical screening) — calibrated on HC3 |

Kaggle is fine **only** as a mirror of the above; verify the source matches the
canonical benchmark and labels.

## Hygiene checklist

- [ ] Balanced classes (≥ a few hundred per class for a stable fit; the gate
      refuses < 20 / < 5-per-class).
- [ ] Distribution match — calibrate the diffusion detector on AI-vs-real *images*,
      not faces-only, unless faces are your deployment domain.
- [ ] Held-out validation (the gate does a 70/30 split); report ECE/Brier/FPR.
- [ ] Adopt only on the gate's `ADOPT` verdict; keep the conservative default
      otherwise.
- [ ] Record dataset name + version + licence alongside the persisted model
      (`storage/calibration_models/<agent>/...`) for court-defensibility.

## What calibration will NOT fix

- **Capability gaps** — calibration rescales an existing detector's scores; it
  cannot create a detector where none exists (it took adding `ai_text_detector.py`
  to make Agent5 calibratable). A missing modality needs a model, not data.
- **Detector ceilings** — a synthesis method the detector cannot physically
  perceive stays undetected regardless of calibration; upgrade the detector.
