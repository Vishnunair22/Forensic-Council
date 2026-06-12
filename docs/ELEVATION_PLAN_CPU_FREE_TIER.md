# Elevation Plan — Investigation & Report Quality Under Current Constraints

**Date:** 2026-06-11
**Constraints honored:** CPU-only inference, Gemini free tier (10 RPM / 1,500 RPD), Groq free tier (30 RPM / ~12K TPM), no new models beyond what the repo already ships or can run on CPU.
**Relationship to existing docs:** builds on `docs/audits/CORE_PIPELINE_AUDIT_2026-06-11.md` and `docs/CALIBRATION_PLAN.md`. This plan selects and sequences only the items achievable with the current setup, with primary focus on **fine-tune optimisation and refinement** (calibration, threshold fitting, weight sourcing, prompt optimization) rather than new capability.

**Core thesis:** the highest-ROI "fine-tuning" available to this system is not neural fine-tuning at all — it is (a) Platt/isotonic calibration of existing detector scores, (b) empirical threshold and weight fitting on labeled subsets, and (c) prompt/token-budget refinement. All three are CPU-trivial (calibration fits 2 parameters per agent), and they attack the single largest quality gap: every confidence number currently shipped is an uncalibrated engineering default.

---

## Phase 0 — Zero-cost correctness fixes (week 1, pure code)

These directly raise finding quality with no data, no API budget, no compute.

| # | Fix | Where | Why it elevates findings |
|---|-----|-------|--------------------------|
| 0.1 | Delete the runtime 5-row IsolationForest fit; replace with transparent rule scores | `tools/ml_tools/exif_isolation_forest.py:95–106` | Removes a statistically meaningless score from verdict inputs |
| 0.2 | Remove forced anomaly ≥ 0.58 when EXIF absent — absence of metadata is INFO, not signal | `exif_isolation_forest.py:118–119` | Kills the built-in false positive on screenshots/social-media exports |
| 0.3 | Signal-family fusion: group tools into families (compression-artifact, boundary, generative, metadata, semantic); count each family once at max confidence; delete the +0.05/signal volume bonus | `arbiter_verdict.py:447–451` | Stops correlated recompression tools co-firing into an inflated MANIPULATED |
| 0.4 | Fix dead logic: single-signal cap 0.45 makes `SINGLE_SIGNAL_MANIP_THRESHOLD=0.85` unreachable. Replace with tiered rule: validated high-reliability tools may alone reach SUSPICIOUS; weak tools need a different-family corroborator | `arbiter_verdict.py:467–468`, `forensic_policy.py:85` | Verdict engine behaves as documented |
| 0.5 | Treat a failed/gated **critical** tool as lost coverage ("X could not be verified"), not "no anomaly" | `arbiter_deliberation.py:294–303` | Removes silent-clean bias — the most court-dangerous defect |
| 0.6 | Capability manifest per investigation: snapshot every applicable tool → {ran, failed, gated_off, model_unavailable} + model name/version; embed in signed report | pipeline start + `deterministic_report_builder.py` | One structure fixes all silent-degradation findings (M2/M3/M4/C9) |
| 0.7 | Print the existing court-inadmissibility statement (`calibration.py:520–529`) in Reliability Notes whenever a contributing model is UNCALIBRATED; label confidence "indicative (uncalibrated)" | report builder | Honest until Phase 1 flips agents to TRAINED |
| 0.8 | Wire `face_swap_detect_deepface` (already implemented + unit-tested at `tools/video_tools.py:689`) into the production path; DeepFace runs CPU-fine on sampled frames | `agent4_video.py` task list | Free real-ML upgrade for the weakest modality — code already exists |
| 0.9 | Apply screenshot gating inside `compute_agent_verdict` (currently arbiter-only), so agent-phase verdicts agree with final | `severity.py` | Removes agent-vs-arbiter verdict drift users see in the UI |
| 0.10 | Rename/annotate misnamed tools in report output: `neural_*`, `f3_net`, `mantra`, `synthid_detect` must state actual method when the research weights aren't loaded | report formatting | Truth in reporting; protects you on cross-examination |

**Gate:** WhatsApp-re-encoded authentic JPEG and a no-EXIF screenshot regression-test as AUTHENTIC/INCONCLUSIVE, never SUSPICIOUS. A run with one tool failure says so in the report.

---

## Phase 1 — Calibration execution: the actual fine-tune (weeks 1–3, CPU-only)

This is the centerpiece. Platt scaling = fitting 2 parameters (A, B) per agent via the existing `calibration_trainer.py`. Compute cost is seconds; the only real cost is scoring labeled media through the detectors once (CPU, batchable overnight). **A few hundred samples per class is sufficient for a stable 2-parameter fit** — you do not need GenImage's 2.7M images.

Order of attack (easiest-unblocked first, per `CALIBRATION_PLAN.md`):

1. **Agent5 (text)** — `calibration_data/text/` already has 100 HC3 samples on disk and `scripts/fetch_hc3_text.py` exists. Wire `tools/ml_tools/ai_text_detector.py` into `collect_calibration_scores.py` (the plan notes Agent5 has no collector wiring — the detector exists, it's just not connected). Expand to ~500/class with HC3 + a RAID sample (`load_dataset("liamdugan/raid", streaming=True)` — stream, don't download 10M docs). Fit, validate, adopt on ADOPT verdict only.
2. **Agent1 (AI-gen images)** — `./acquire_calibration_datasets.sh agent1`; sample a **balanced ~1,000–2,000 image subset stratified across generators** (don't calibrate to one generator's artifacts). ViT detector inference on 2K images is a few CPU-hours — run via the existing `ml_subprocess` pool overnight.
3. **Agent3 (splicing)** — CASIA v2 (`agent3`), sample ~1,000/class. Since `ENABLE_RESEARCH_MODELS=true` in the current `.env`, calibrate the **TruFor path** (the one that actually runs) — calibration is config-specific; record `research_models: on` next to the persisted model.
4. **Agent2 (audio)** — ASVspoof 2021 DF subset (~500/class, codec-processed split since it matches deployment).
5. **Agent4 (video)** — needs a collector runner first (small code change: wire `interframe_forgery_detector`/`deepfake_frequency` scores into the collector). FF++/DFDC are EULA-gated — apply now, calibrate when granted. Until then Agent4 confidence stays labeled uncalibrated.

### 1b. Threshold & weight fitting (same data, bigger payoff than Platt alone)

While the collector runs, persist **raw scores per tool**, not just the calibration pair. Then:

- **Per-tool ROC sweep:** for every tool with a magic threshold (copy_move 35.0, splicing ratio 0.05, diffusion spike 18.0, deepfake_frequency 0.4, IF contamination 0.015/0.15, lighting 0.42/0.46…), compute TPR/FPR across the threshold range on the labeled subset. Set thresholds at a chosen FPR operating point (suggest FPR ≤ 0.05 for alert signals, ≤ 0.01 for "strong" signals). Write the measured (threshold, TPR, FPR) into the capability manifest so reports can disclose per-tool error rates.
- **Source `forensic_policy.py` weights from AUC:** replace the unsourced weight table (heuristic neural_ela at 1.0 vs ela_full_image 0.65) with weights proportional to measured per-tool AUC on the calibration subset; tools with AUC < 0.6 get weight ≤ 0.3 and can never be a "strong" signal alone.
- **Isotonic fallback:** if Platt's sigmoid fits poorly (detector scores are often bimodal), fit `sklearn.isotonic.IsotonicRegression` on the same scores — equally CPU-trivial; adopt whichever wins on ECE+Brier under the existing `validate_calibration.py` gate.
- **Severity bands re-derived:** the 0.60/0.75 severity cut-points and the 0.94/0.85 verdict constants in `severity.py:244–256, 419–422` should be re-derived from the calibrated score distributions (e.g., set CRITICAL at the score where measured precision ≥ 0.9) and documented with the validation curve.

**Gate:** ≥3 agents flip to `CalibrationStatus.TRAINED`; every alert-capable tool has a recorded (TPR, FPR) at its operating threshold; CI regression corpus (≥300 items to start: authentic camera, re-encodes, screenshots, AI-gen, spliced) runs per-category FPR checks.

---

## Phase 2 — LLM layer refinement within free tier (weeks 2–4)

Groq math today: 5 per-agent syntheses ≈ 15–22K tokens vs 12K TPM — **every typical investigation overruns ~25%** and silently degrades (`llm_client.py:726–772`). Fixes:

1. **Batch synthesis as the only path:** `refine_synthesis_batch` already exists (`arbiter.py:426, 609`) — make it canonical. 1 call instead of 5.
2. **Model routing by job:** synthesis → `llama-3.1-8b-instant` (cheap, plentiful); reserve `llama-3.3-70b` exclusively for the final refiner. Cap synthesis `max_tokens` 1500→1000 and feed pre-summarized `(tool, key_metrics, confidence)` tuples instead of raw output.
3. **Per-investigation token budget** in `quota_manager.py`: refiner reserve ~4.8K; synthesis calls that would invade the reserve fall back to template **with a provenance tag** (never silently).
4. **Persist quota state in Redis** (`provider_quota_guard.py` is process-local — resets on restart, wrong under multiple workers).
5. **Prompt refinements (no token-cost increase, mostly quality-per-token):**
   - Few-shot examples in the Gemini vision preflight (currently zero-shot → hallucinated fields). 2 compact exemplars suffice.
   - Stop truncating tool results to 260 chars before Groq synthesis — truncation is what makes the model fabricate metrics. Structured tuples (above) fix both the token cost and the hallucination source at once.
   - Enum-constrained JSON everywhere: Gemini `responseSchema` and Groq JSON mode are both free-tier features. Then **delete the substring-keyword taxonomy** (`manipulation_signal_taxonomy.py:64–80`) — LLM free text should never reach verdict inputs.
   - Brief chain-of-thought field (`"reasoning"`) before the structured fields in the schema — cheap, measurably improves structured accuracy at T=0.1.
   - Post-generation validation: every numeric claim in refined narrative must match a tool output (string-match against findings table); reject and retry once, else fall back to deterministic text.
   - Inject the EXIF/metadata summary into the vision prompt so Gemini's visual read is grounded in the same context the agents have.
6. **Gemini RPM=5–10 is the bottleneck:** downscale images before upload, key the visual-context cache on content hash (exists — `visual_context_store.py`) and disclose cache source/age in the report instead of hiding it.

**Gate:** 50-investigation soak with zero silent LLM degradations; all fallbacks visible in metrics and reports; refiner never starved.

---

## Phase 3 — Report elevation (weeks 3–5, depends on Phase 1 outputs)

What makes the report read like a professional forensic document, all code/prompt-only:

1. **Methodology section** generated from the capability manifest: tools run, model+version each, what each measures, per-tool (TPR, FPR) from Phase 1b.
2. **Likelihood-ratio language** instead of raw posteriors: "the observed artifacts are N× more likely under manipulation than under authentic capture" — avoids the base-rate fallacy and matches how forensic conclusions are actually defended.
3. **Calibration disclosure block:** TRAINED agents cite dataset name/version/license (already stored with the model); UNCALIBRATED agents carry the court statement.
4. **Surface existing heatmaps:** TruFor/BusterNet localization maps are computed and discarded — attach them to the report/UI. Visual evidence is the single most persuasive artifact for a human reviewer and it's already paid for.
5. **Whitelist narrative generation:** every report sentence traces to a finding ID or carries a `[narrative]` tag; delete the superlative phrase-bank in `arbiter_narrative.py` and the canned "consistent with an unmodified original" line.
6. **Limitations section, auto-generated:** failed tools, gated models, cached visual context (source + age), uncalibrated contributors, coverage percentage, and the per-format exclusions (e.g., animated GIF skips splicing).
7. **Reproducibility block:** model versions, prompt hashes, temperature/seed, `reproducibility: deterministic|LLM-assisted` per section.
8. **Verdict qualification:** when coverage < 70% or any critical-tool failure occurred, the executive summary's first sentence states the limitation before the verdict.

---

## Explicitly out of scope (constraint-driven)

- **No neural fine-tuning of detector weights** (TruFor/ViT LoRA etc.) — not feasible on CPU and not the bottleneck; calibration + thresholds capture most of the available accuracy honesty.
- **No new heavyweight detectors** (SyncNet lip-sync, FF++-class video classifiers) until hardware changes — Agent4 elevation is limited to wiring DeepFace (0.8), the collector runner, and honest disclosure.
- **No paid API tiers.** All LLM improvements above *reduce* token consumption.

## Sequencing

| Week | Work | Outcome |
|------|------|---------|
| 1 | Phase 0 (all), start Agent5+Agent1 data | Verdict math defensible; reports honest |
| 2–3 | Phase 1 fits + ROC sweeps; Phase 2 items 1–4 | TRAINED calibration for agents 1/3/5; no silent LLM degradation |
| 3–4 | Phase 2 prompts; Agent2 calibration | Grounded, schema-locked LLM output |
| 4–5 | Phase 3 report work; regression corpus in CI | Reports cite measured error rates with visual evidence |

**Bottom line:** nothing here needs new hardware or paid tiers. After Phase 0 the system stops overstating; after Phase 1 its numbers mean something; after Phases 2–3 the reports earn the confidence they state.
