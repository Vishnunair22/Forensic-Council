# Calibration Plan & Dataset Acquisition Guide

**Goal:** make every agent's confidence number honest and every verdict defensible, by
fitting each per-agent Platt sigmoid on a **clean, known-provenance, correctly-licensed**
labelled benchmark — then adopting it **only** if it beats the conservative default on the
existing safety gate (`validate_calibration.py`). This is calibration, not retraining: we
rescale raw detector scores; we do not touch the underlying detectors.

**Current state (verified in code):** all five agents ship `CalibrationStatus.UNCALIBRATED`
engineering defaults (`core/calibration.py`). On disk only `Agent1`, `Agent3`, `Agent5` have
model folders; `Agent2`/`Agent4` fall back to in-code defaults. The collector
(`scripts/collect_calibration_scores.py`) wires only three detectors today —
`ai_generation`, `splicing`, `voice_clone`. **Agent4 has no collector runner and Agent5 has
no local AI-text detector** — both are engineering gaps, not data gaps.

---

## 1. Per-agent order, wiring, and what blocks calibration

Order is 1→5 as requested. "Blocker" is the thing that must be true before calibration can run.

| # | Agent | Detector (`--detector`) | Score key | Calib key | On-disk model? | Blocker before calibration |
|---|-------|------------------------|-----------|-----------|----------------|----------------------------|
| 1 | Agent1 image AI-gen | `ai_generation` | `diffusion_probability` | `agent1_image` | yes (default) | none — data only |
| 2 | Agent2 audio voice-clone | `voice_clone` | `clone_probability` | `agent2_audio` | no | none — data only |
| 3 | Agent3 splicing/tamper | `splicing` | `splicing_score` | `agent3_object` | yes (default) | none — data only |
| 4 | Agent4 video deepfake | **missing** | — | `agent4_video` | no | **add a collector runner** (e.g. `interframe_forgery_detector` / `deepfake_frequency`) before any data helps |
| 5 | Agent5 AI-text/metadata | **none** | — | `agent5_metadata` | yes (default) | **add an AI-text detector** (no local model exists); calibration cannot create one |

So agents 1–3 are calibratable today with data alone. Agent 4 needs a small code change first.
Agent 5 needs a real detector first — see §5.

---

## 2. Dataset acquisition guide (assessed, current as of June 2026)

Pick datasets with **known provenance and licence** — the calibration set becomes part of the
methodology you defend in court. Random "deepfake.zip" Kaggle uploads with dubious labels
calibrate to noise. For each agent below: the recommended benchmark, the licence, where to get
it, and a provenance note.

### Agent 1 — AI-generated images
- **GenImage** (primary). ~2.7M images: full ImageNet-1k validation set as the *real* side,
  paired ~1:1 with synthetic images from Midjourney, Stable Diffusion, ADM, GLIDE, Wukong,
  VQDM, BigGAN. Balanced per generator.
  - Licence: **CC BY-NC-SA 4.0** (non-commercial — confirm this fits your use).
  - Get it: official repo/site (links in §7); paper arXiv:2306.08571.
  - Provenance: strong — real side is ImageNet-1k val (citable), synthetic side is generator-labelled.
- **Supplement for generator coverage:** Synthbuster and DRCT-2M to cover newer diffusion
  generators GenImage predates. Balance generators so you don't calibrate to one model's artifacts.
- **Real-side balance:** COCO / ImageNet subsets.

### Agent 2 — Synthetic / cloned voice
- **ASVspoof 2021 DF** (primary) + **ASVspoof 2019 LA**. DF = bona-fide vs TTS/VC spoof
  processed through lossy codecs (closest to deployment); 2019 LA adds clean modern TTS/VC.
  - Licence: **Open Data Commons Attribution** — permissive, court-friendly.
  - Get it: Zenodo record 4835108; eval keys / meta-labels from asvspoof.org (links in §7).
  - Provenance: strong — challenge-grade labels, widely cited, version-pinnable.

### Agent 3 — Image splicing / tamper
- **CASIA v2.0** (start here — easiest access): 7,200 authentic + 5,123 spliced/forged images.
- **DEFACTO** (scale, COCO-sourced) and **NIST MFC2018/MFC2019** (court-grade, but **require
  NIST registration**).
  - Licences vary per set; NIST requires registration and version citation.
  - Get it: CASIA via forensics.idealtest.org; NIST MFC via nist.gov MFC pages (links in §7).
  - Provenance: NIST MFC is the gold standard for defensibility; CASIA is fine to wire the
    pipeline and get a first honest fit.
  - **Distribution note:** calibrate the splicing detector on splice-vs-authentic *photographs*,
    matching your deployment domain — not faces-only.

### Agent 4 — Video deepfake (needs a collector runner first — §5)
- **FaceForensics++** (c23 and c40 compression): 1,000+ real videos + manipulated versions
  (DeepFakes, Face2Face, FaceSwap, NeuralTextures).
- **Celeb-DF v2** (5,600+ videos, low-artifact) and **DFDC** (professional actors, controlled).
  - Licence/access: all three are **EULA / request-form gated** — you must apply and agree to
    terms (research-use, no redistribution). Budget lead time.
  - Provenance: strong and standard; sample a *balanced* subset (these are large).

### Agent 5 — AI-generated text (needs a detector first — §5)
- **RAID** (primary, ACL 2024): ~10M docs, 11 LLMs, 11 genres, 4 decoding strategies, 12
  adversarial attacks — the most robust current benchmark. `load_dataset("liamdugan/raid")`.
- **HC3** (human-vs-ChatGPT, ~27k Q&A across reddit/medicine/finance/law) and **M4GT-Bench**
  (multilingual) as supplements.
  - Licence: check each repo's terms before adopting into methodology (RAID/HC3 on GitHub/HF).
  - Provenance: RAID labels are construction-time ground truth — strong.

---

## 3. Hygiene gates (enforced by the scripts — do not bypass)

- **Balance:** ≥ a few hundred per class for a stable fit. The gate hard-refuses < 20 total or
  < 5 per class.
- **Distribution match:** calibrate each detector on data resembling deployment (AI-vs-real
  *images* for the diffusion detector, splice-vs-authentic *photos* for splicing, etc.).
- **Held-out validation:** `validate_calibration.py` does a 70/30 split and reports ECE / Brier / FPR.
- **Adopt-only-if-it-beats-default:** persist a trained model **only** on the gate's `ADOPT`
  verdict (trained beats default on **both** ECE and Brier **and** does not raise FPR at the
  0.5 decision point). Otherwise keep the conservative default.
- **Record for court:** dataset name + version + licence stored alongside the persisted model
  in `storage/calibration_models/<Agent>/`.

---

## 4. Execution recipe (run inside the worker container — ML models present; Docker worker is up)

Per agent, with a labelled benchmark laid out as `real/` (authentic) and `fake/` (AI/manipulated)
directories, or a `path,label` manifest:

```bash
# 1. Collect raw detector scores over the LABELLED benchmark (0=authentic, 1=AI/manipulated)
python scripts/collect_calibration_scores.py \
    --detector ai_generation \
    --real /data/genimage/real --fake /data/genimage/ai \
    --out /tmp/agent1_ai_scores.csv

# 2. SAFETY GATE — fit on train split, compare to default on held-out test. Writes nothing.
python scripts/validate_calibration.py --dataset /tmp/agent1_ai_scores.csv --agent agent1_image
#   → VERDICT: ADOPT          (trained beats default on ECE+Brier, FPR not worse)
#   → VERDICT: KEEP_DEFAULT   (otherwise — stop, do not persist)

# 3. Persist ONLY if step 2 said ADOPT
python scripts/train_calibration.py --dataset /tmp/agent1_ai_scores.csv \
    --agent agent1_image --output-dir storage/calibration_models
```

Swap `--detector` / `--agent` per row in §1: `splicing`/`agent3_object`,
`voice_clone`/`agent2_audio`. Calibrate **per agent / per detector** — each needs data matching
what it detects.

---

## 5. What calibration will NOT fix (engineering work, not data)

- **Agent 4 (video):** `collect_calibration_scores.py` has no video runner. Add one to the
  `DETECTORS` map (wrap `interframe_forgery_detector` or `deepfake_frequency` to emit a 0–1 score
  and `_VIDEO_EXTS`) before FaceForensics++/DFDC data can produce a CSV.
- **Agent 5 (text):** there is **no local AI-text detector** — calibration data cannot create
  a detector. Add one first (a deployable open model such as **Binoculars** or **RADAR**, or a
  Gemini path), expose a `score`, wire it into the collector, *then* calibrate on RAID/HC3.
- **Detector ceilings:** a synthesis method a detector physically cannot perceive stays
  undetected regardless of calibration — that calls for a stronger detector, not more data.

---

## 6. Recommended sequencing

1. **Agent 1, then Agent 3** — both calibratable today, easiest data (CASIA for Agent3, GenImage
   for Agent1). Fastest path to two honestly-calibrated agents and a proven end-to-end loop.
2. **Agent 2** — ASVspoof download is permissive and quick; calibrate once Agent1/3 loop is proven.
3. **Agent 4** — start the FF++/DFDC/Celeb-DF v2 **access requests now** (EULA lead time), and in
   parallel add the video collector runner.
4. **Agent 5** — decide detector strategy (Binoculars/RADAR vs Gemini), implement it, then
   calibrate on RAID. Largest effort; do last.

---

## 7. Source links

- GenImage: https://genimage-dataset.github.io/ · https://github.com/GenImage-Dataset/GenImage · paper https://arxiv.org/abs/2306.08571
- ASVspoof 2021: https://zenodo.org/records/4835108 · https://www.asvspoof.org/index2021.html
- Splicing: CASIA http://forensics.idealtest.org/ · NIST MFC2018 https://www.nist.gov/itl/iad/mig/media-forensics-challenge-2018 · MFC resources https://mfc.nist.gov/ · dataset index https://github.com/greatzh/Image-Forgery-Datasets-List
- Video deepfake: FaceForensics++ / DFDC / Celeb-DF v2 — survey & links https://www.mdpi.com/2079-9292/13/3/585 · Celeb-DF overview https://www.emergentmind.com/topics/celeb-df-dataset
- AI text: RAID https://github.com/liamdugan/raid · paper https://arxiv.org/abs/2405.07940

---

## 8. Findings & fixes from the calibration audit (2026-06-11)

Before any dataset work, a dry-run of the gate surfaced a **critical bug that would have made
every "calibrated" model unsound** — now fixed.

### 8.1 `fit_platt` ran gradient *ascent* (diverged) — FIXED
`scripts/train_calibration.py::fit_platt` subtracted the gradient when it should add it for this
sigmoid parameterisation (`p = 1/(1+exp(A·x+B))`), so it **maximised** the negative
log-likelihood instead of minimising it. Result: `A` ran off toward ±∞ and the fit was useless.

- Proof: on a clean, well-separated synthetic set (authentic scores ~0.22, manipulated ~0.78),
  the old code gave `A=+954, accuracy=0.500` (random). The corrected descent gives
  `A=-17.07, accuracy≈1.000, ECE 0.218 → 0.029, TPR 0.997 / FPR 0.003`.
- Also bumped the under-tuned defaults (`lr 0.01→0.3`, `max_iter 200→5000`) and added a
  gradient-norm stopping tolerance, because even with the correct sign the old hyperparameters
  under-converged (acc 0.17).
- Train and inference conventions match (`core/calibration.py:504` uses the same
  `1/(1+exp(A·x+B))`), so a model trained by the fixed script applies correctly at inference.

Implication: any calibration trained before this fix should be **discarded and refit**. The
on-disk defaults remain UNCALIBRATED and are unaffected.

### 8.2 Engineering defaults are *decreasing* in the score
All in-code defaults use `A>0`, which makes `1/(1+exp(A·x+B))` decrease as the detector's
evidence rises — i.e. an agent running on the UNCALIBRATED default reports confidence
*anti-correlated* with its own detector. This is "conservative" only in that it suppresses
output; it is not neutral. It resolves automatically once a real model is trained+adopted
(fitted `A` goes negative). Until then, treat default-backed confidence as not meaningful.

### 8.3 Agent 4 video collector runner — ADDED
`collect_calibration_scores.py` now has a `deepfake_video` detector wired to
`interframe_forgery_detector.analyze_interframe_consistency` (score = `interframe_probability`,
`_VIDEO_EXTS` = mp4/mov/avi/mkv/webm/m4v). Agent 4 is now calibratable end-to-end once
FaceForensics++/DFDC/Celeb-DF v2 footage is laid out as `--real`/`--fake` dirs:

```bash
python scripts/collect_calibration_scores.py --detector deepfake_video \
    --real /data/ff++/real --fake /data/ff++/fake --out /tmp/agent4_video_scores.csv
python scripts/validate_calibration.py --dataset /tmp/agent4_video_scores.csv --agent agent4_video
# adopt only on ADOPT:
python scripts/train_calibration.py --dataset /tmp/agent4_video_scores.csv \
    --agent agent4_video --output-dir storage/calibration_models
```

### 8.4 Optional hardening (not blocking)
The gate adopts a trained model whenever it beats the default on ECE+Brier without raising FPR.
On a genuinely *uninformative* detector (overlapping classes) it still adopts, because honest
near-base-rate probabilities beat the miscalibrated default. That is acceptable, but if you want
the gate to refuse uninformative detectors outright, add a minimum-separation floor (e.g. require
test-split AUC ≥ ~0.6) alongside the ECE/Brier/FPR checks.
