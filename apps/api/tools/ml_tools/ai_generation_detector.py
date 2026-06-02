#!/usr/bin/env python3
"""
ai_generation_detector.py
==========================
REAL AI / diffusion image detection using a pretrained Vision Transformer
classifier (Hugging Face ``AutoModelForImageClassification``).

Unlike the spectral heuristics (``diffusion_artifact_detector.py``,
``f3net_freq.py``), this loads an *actual trained model* whose weights encode
learned generative-artifact features from SDXL/SD3/Flux/Midjourney-class
images. It is the primary AI-generation signal; the spectral tools become
corroboration when the model is available.

Honesty contract:
  • The result reports the real ``model_id`` it ran — never a fabricated name.
  • If the model/weights cannot be loaded (offline with no cache, missing
    transformers, OOM), it returns ``available: False`` with a plain reason so
    the caller degrades to the spectral heuristic and the finding is recorded
    as a coverage gap, never a fabricated clean result.

Runs CPU-only, single image, in the isolated ml_subprocess (RLIMIT_AS bounded).

Output schema (compatible with diffusion_artifact_detector_handler):
    {
        "diffusion_probability": 0.91,   # P(AI-generated)
        "confidence": 0.91,
        "is_ai_generated": true,
        "verdict": "GEN_AI_DETECTION" | "SUSPICIOUS" | "NATURAL_OR_CLEAN",
        "predicted_label": "artificial",
        "model_id": "Organika/sdxl-detector",
        "method": "vit_classifier",
        "available": true,
        "court_defensible": true
    }

Usage:
    python ai_generation_detector.py --input /path/to/image.jpg
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Default permissive, CPU-feasible ViT detector tuned for modern diffusion
# output. Operators may override via AI_IMAGE_DETECTOR_MODEL. License of any
# third-party checkpoint must be verified by the operator before commercial use.
_DEFAULT_MODEL = os.getenv("AI_IMAGE_DETECTOR_MODEL", "Organika/sdxl-detector")

# Label tokens that indicate the *AI-generated* class vs the *authentic* class.
_AI_TOKENS = ("artificial", "ai", "fake", "synthetic", "generated", "gan", "diffusion")
_REAL_TOKENS = ("human", "real", "authentic", "natural", "genuine", "nonai", "not")

_model = None
_processor = None
_load_error: str | None = None


def _offline() -> bool:
    try:
        from core.config import get_settings

        return bool(get_settings().offline_mode)
    except Exception:
        return os.getenv("HF_HUB_OFFLINE") == "1" or os.getenv("TRANSFORMERS_OFFLINE") == "1"


def _load():
    """Lazily load the detector. Sets _load_error (honest reason) on failure."""
    global _model, _processor, _load_error
    if _model is not None or _load_error is not None:
        return
    try:
        import torch  # noqa: F401
        from transformers import AutoImageProcessor, AutoModelForImageClassification

        # Keep CPU threads modest so concurrent tools don't oversubscribe cores.
        try:
            import torch as _t

            _t.set_num_threads(max(1, (os.cpu_count() or 2) // 2))
        except Exception:
            pass

        offline = _offline()
        _processor = AutoImageProcessor.from_pretrained(_DEFAULT_MODEL, local_files_only=offline)
        _model = AutoModelForImageClassification.from_pretrained(
            _DEFAULT_MODEL, local_files_only=offline
        )
        _model.eval()
    except Exception as exc:  # noqa: BLE001 — any failure must degrade gracefully
        _load_error = str(exc)
        _model = None
        _processor = None


def _class_is_ai(label: str) -> bool | None:
    """Return True if label denotes AI-generated, False if authentic, None if ambiguous."""
    low = label.strip().lower()
    if any(tok in low for tok in _AI_TOKENS):
        # "not ai" / "nonai" should map to authentic — guard against that.
        if "not" in low or "non" in low:
            return False
        return True
    if any(tok in low for tok in _REAL_TOKENS):
        return False
    return None


def detect(image_path: str) -> dict:
    _load()
    if _model is None or _processor is None:
        return {
            "available": False,
            "degraded": True,
            "error": f"AI-generation model unavailable: {_load_error or 'transformers/weights missing'}",
            "model_id": _DEFAULT_MODEL,
            "method": "vit_classifier",
        }

    try:
        import torch
        from PIL import Image

        # Cap resolution to bound memory; the processor resizes to model input anyway.
        image = Image.open(image_path).convert("RGB")
        longest = max(image.width, image.height)
        if longest > 2560:
            scale = 2560 / float(longest)
            image = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))))

        inputs = _processor(images=image, return_tensors="pt")
        with torch.no_grad():
            logits = _model(**inputs).logits
            probs = torch.softmax(logits, dim=-1)[0]

        id2label = getattr(_model.config, "id2label", {}) or {}
        ai_prob = None
        ambiguous = False
        per_label = {}
        for idx in range(probs.shape[0]):
            label = str(id2label.get(idx, id2label.get(str(idx), f"LABEL_{idx}")))
            p = float(probs[idx].item())
            per_label[label] = round(p, 4)
            verdict_bit = _class_is_ai(label)
            if verdict_bit is True:
                ai_prob = (ai_prob or 0.0) + p
            elif verdict_bit is None:
                ambiguous = True

        # Fallback when labels are opaque (LABEL_0/LABEL_1): take the higher-index
        # class as the positive (AI) class — convention for these binary detectors —
        # but flag reduced defensibility.
        if ai_prob is None:
            ambiguous = True
            ai_prob = float(probs[-1].item()) if probs.shape[0] >= 2 else float(probs[0].item())

        ai_prob = max(0.0, min(1.0, ai_prob))
        top_idx = int(torch.argmax(probs).item())
        predicted_label = str(id2label.get(top_idx, f"LABEL_{top_idx}"))

        if ai_prob > 0.6:
            verdict = "GEN_AI_DETECTION"
        elif ai_prob > 0.45:
            verdict = "SUSPICIOUS"
        else:
            verdict = "NATURAL_OR_CLEAN"

        return {
            "diffusion_probability": round(ai_prob, 3),
            "confidence": round(ai_prob, 3),
            "is_ai_generated": ai_prob > 0.6,
            "verdict": verdict,
            "predicted_label": predicted_label,
            "label_probabilities": per_label,
            "model_id": _DEFAULT_MODEL,
            "method": "vit_classifier",
            "available": True,
            # A real trained model is court-defensible; flag down if label mapping
            # had to guess, so the report can caveat it honestly.
            "court_defensible": not ambiguous,
            "label_mapping_ambiguous": ambiguous,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "available": False,
            "degraded": True,
            "error": f"AI-generation inference failed: {exc}",
            "model_id": _DEFAULT_MODEL,
            "method": "vit_classifier",
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Real ViT AI-generation detector")
    parser.add_argument("--input", type=str, help="Path to input image")
    parser.add_argument("--warmup", action="store_true", help="Warmup mode - preload model")
    parser.add_argument("--worker", action="store_true", help="Worker mode - persistent process")
    args = parser.parse_args()

    if args.warmup:
        _load()
        if _model is not None:
            print(json.dumps({"status": "warmed_up", "model_id": _DEFAULT_MODEL}))
            sys.exit(0)
        # Warm-up "failure" is non-fatal — the tool degrades to the spectral
        # heuristic at call time. Report it without a non-zero exit so the
        # warm-up orchestrator doesn't treat it as a hard error.
        print(json.dumps({"status": "warmup_degraded", "error": _load_error, "model_id": _DEFAULT_MODEL}))
        sys.exit(0)

    if args.worker:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
                input_path = request.get("input")
                if not input_path:
                    print(json.dumps({"error": "Missing input path", "available": False}))
                    sys.stdout.flush()
                    continue
                print(json.dumps(detect(input_path)))
                sys.stdout.flush()
            except Exception as e:  # noqa: BLE001
                print(json.dumps({"error": str(e), "available": False}))
                sys.stdout.flush()
        sys.exit(0)

    if not args.input:
        parser.print_help()
        sys.exit(1)

    try:
        print(json.dumps(detect(args.input)))
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"error": str(e), "available": False}))
