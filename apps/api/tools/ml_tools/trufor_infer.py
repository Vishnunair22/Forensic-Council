"""Real TruFor (GRIP-UNINA, CVPR'23) splicing detector — inference wrapper.

Vendored model code lives in ``trufor_pkg/models`` (the authors' test_docker/src,
non-commercial license). Weights (``trufor.pth.tar``, ~261MB) are downloaded to
the model cache. This module builds the model once per process, runs inference,
and maps TruFor's outputs to the schema the neural_splicing handler expects:

    pred (softmax[1]) -> per-pixel forgery localization map
    det  (sigmoid)    -> whole-image integrity/forgery score  ← primary signal
    conf (sigmoid)    -> reliability map

Replaces the previous IsolationForest heuristic, which fired on every image.
Falls back gracefully (returns available=False) if weights are missing so the
caller can use its heuristic fallback.
"""
from __future__ import annotations

import os
import sys

_THIS_DIR = os.path.dirname(os.path.realpath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

_WEIGHTS_CANDIDATES = [
    os.environ.get("TRUFOR_WEIGHTS", ""),
    "/app/cache/trufor/trufor.pth.tar",
    "/tmp/trufor/trufor.pth.tar",
]
_MAX_SIDE = 512  # cap long side: SegFormer-B2 on CPU is ~4x faster at 512 vs 1024;
# the global detection score (primary signal) stays discriminative at this size.

_model = None
_model_failed = False


class _N(dict):
    """Minimal yacs-CfgNode stand-in: attribute access + dict `in` membership."""

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError as e:
            raise AttributeError(k) from e

    __setattr__ = dict.__setitem__


def _build_cfg():
    return _N(
        MODEL=_N(
            NAME="detconfcmx",
            PRETRAINED="",  # full checkpoint loaded below, no per-branch pretrain
            MODS=("RGB", "NP++"),
            EXTRA=_N(
                BACKBONE="mit_b2",
                DECODER="MLPDecoder",
                DECODER_EMBED_DIM=512,
                PREPRC="imagenet",
                BN_EPS=0.001,
                BN_MOMENTUM=0.1,
                DETECTION="confpool",
                CONF=True,
            ),
        ),
        DATASET=_N(NUM_CLASSES=2),
    )


def _weights_path():
    for p in _WEIGHTS_CANDIDATES:
        if p and os.path.isfile(p):
            return p
    return None


def _research_models_enabled() -> bool:
    """TruFor weights are non-commercial (GRIP-UNINA). Only load when research
    models are enabled (ENABLE_RESEARCH_MODELS=true). When disabled, analyze()
    returns unavailable and the caller falls back to its heuristic path."""
    try:
        from core.config import get_settings

        return bool(get_settings().enable_research_models)
    except Exception:
        return False


def _load_model():
    global _model, _model_failed
    if _model is not None:
        return _model
    if _model_failed:
        return None
    if not _research_models_enabled():
        _model_failed = True
        return None
    wp = _weights_path()
    if wp is None:
        _model_failed = True
        return None
    try:
        import torch

        # ML subprocesses run with OMP/BLAS capped to 1 thread (crash safety for
        # many concurrent small tools). TruFor is a single heavy 68M-param model;
        # single-threaded CPU inference is far too slow (>60s). Let torch use a few
        # threads to keep it ~10-20s, bounded so two concurrent deep runs don't
        # thrash all cores.
        try:
            import os as _os

            torch.set_num_threads(max(2, min(4, (_os.cpu_count() or 2))))
        except Exception:
            pass

        from trufor_pkg.models.cmx.builder_np_conf import myEncoderDecoder as ConfCMX

        cfg = _build_cfg()
        model = ConfCMX(cfg=cfg)
        # weights_only=False: torch>=2.6 defaults to True, which rejects the
        # official TruFor checkpoint (contains a numpy scalar). The weights are
        # downloaded from the authors' server (trusted source).
        ckpt = torch.load(wp, map_location="cpu", weights_only=False)
        state = ckpt.get("state_dict", ckpt) if isinstance(ckpt, dict) else ckpt
        model.load_state_dict(state)
        model.eval()
        _model = model
        return _model
    except Exception:
        _model_failed = True
        return None


def analyze(image_path: str) -> dict:
    """Run real TruFor. Returns the neural_splicing result schema, or
    available=False (so the caller falls back) if the model can't run."""
    model = _load_model()
    if model is None:
        return {"available": False, "error": "TruFor weights/model unavailable", "model_version": "trufor_real_v1"}

    try:
        import cv2
        import numpy as np
        import torch
        from torch.nn import functional as F

        img = cv2.imread(image_path)
        if img is None:
            return {"available": False, "error": "Cannot read image", "model_version": "trufor_real_v1"}
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h0, w0 = rgb.shape[:2]
        # Cap long side for memory/latency; record scale to map regions back.
        scale = 1.0
        long_side = max(h0, w0)
        if long_side > _MAX_SIDE:
            scale = _MAX_SIDE / float(long_side)
            rgb = cv2.resize(rgb, (int(round(w0 * scale)), int(round(h0 * scale))), interpolation=cv2.INTER_AREA)

        x = torch.from_numpy(rgb.transpose(2, 0, 1)).float().unsqueeze(0) / 256.0
        with torch.no_grad():
            pred, conf, det, _npp = model(x)
        det_sig = float(torch.sigmoid(det).item()) if det is not None else None
        pmap = F.softmax(torch.squeeze(pred, 0), dim=0)[1].cpu().numpy()  # (H,W) forgery prob

        # Localized forgery regions from the map (connected components).
        loc_thresh = 0.5
        mask = (pmap > loc_thresh).astype(np.uint8)
        regions = []
        n_lab, lab = cv2.connectedComponents(mask * 255, connectivity=8)
        inv = 1.0 / scale
        min_area = max(16, int(0.0008 * mask.size))  # ignore speckle (<~0.08% of image)
        for i in range(1, n_lab):
            ys, xs = np.where(lab == i)
            if len(ys) < min_area:
                continue
            regions.append({
                "x": int(xs.min() * inv), "y": int(ys.min() * inv),
                "w": int((xs.max() - xs.min() + 1) * inv), "h": int((ys.max() - ys.min() + 1) * inv),
            })

        score = det_sig if det_sig is not None else float(pmap.max())
        splicing_detected = score >= 0.5
        return {
            "splicing_detected": bool(splicing_detected),
            # Declare the evidence verdict explicitly so the tool-output classifier
            # records it directly (a trained court-defensible detector). Without
            # this it fell through to INCONCLUSIVE and a real splice never raised
            # the agent verdict above Authentic.
            "evidence_verdict": "POSITIVE" if splicing_detected else "NEGATIVE",
            "confidence": round(float(score), 3),
            "detection_score": round(float(score), 3),
            "localization_max": round(float(pmap.max()), 3),
            "localization_mean": round(float(pmap.mean()), 4),
            "forgery_regions": regions[:10],
            "num_forgery_regions": len(regions),
            "verdict": "SPLICED" if splicing_detected else "AUTHENTIC",
            "available": True,
            "court_defensible": True,
            "model_version": "trufor_real_v1",
            "backend": "TruFor CMX (SegFormer-B2 + Noiseprint++)",
        }
    except Exception as e:
        return {"available": False, "error": f"TruFor inference failed: {e}", "model_version": "trufor_real_v1"}
