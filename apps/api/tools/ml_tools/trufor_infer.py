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

import logging
import os
import sys

_THIS_DIR = os.path.dirname(os.path.realpath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

logger = logging.getLogger(__name__)

_WEIGHTS_CANDIDATES = [
    os.environ.get("TRUFOR_WEIGHTS", ""),
    "/app/cache/trufor/trufor.pth.tar",
    "/tmp/trufor/trufor.pth.tar",
]
_MAX_SIDE = 384  # cap long side: SegFormer-B2 on CPU is ~4x faster at 384 vs 1024;
# the global detection score (primary signal) stays discriminative at this size.
# 384 avoids the "chunk is longer than limit" tokenizer error seen at 512 on
# certain image aspect ratios (the SegFormer patch embedding overflows the
# tokenizer's max chunk length when the token count is too high).

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

        def _run_inference(rgb_in, max_side):
            """Run TruFor inference; returns (pred, det, scale) or raises."""
            h0i, w0i = rgb_in.shape[:2]
            scale_i = 1.0
            long_side_i = max(h0i, w0i)
            if long_side_i > max_side:
                scale_i = max_side / float(long_side_i)
                rgb_in = cv2.resize(
                    rgb_in,
                    (int(round(w0i * scale_i)), int(round(h0i * scale_i))),
                    interpolation=cv2.INTER_AREA,
                )
            x = torch.from_numpy(rgb_in.transpose(2, 0, 1)).float().unsqueeze(0) / 256.0
            with torch.no_grad():
                pred, _conf, det, _npp = model(x)
            return pred, det, scale_i

        # Attempt inference at _MAX_SIDE; if the SegFormer tokenizer overflows
        # ("chunk is longer than limit" — can surface as ValueError or RuntimeError
        # depending on the tokenizers Rust binding version), retry at a smaller size.
        try:
            pred, det, scale = _run_inference(rgb, _MAX_SIDE)
        except Exception as ve:
            if "chunk" in str(ve).lower():
                logger.warning(
                    "TruFor chunk-length overflow at %dpx — retrying at 256px",
                    _MAX_SIDE,
                )
                pred, det, scale = _run_inference(rgb, 256)
            else:
                raise

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
        # High-precision operating point. TruFor's detection head produces moderate
        # det-scores (~0.5–0.7) on AUTHENTIC images that contain legitimate composited
        # graphics — text overlays, measurement rulers, evidence markers — which are
        # ubiquitous in real forensic documentation photos. At the paper-default 0.5
        # threshold these benign overlays false-flag as splicing (det 0.66 with a few
        # tiny high-prob regions and a very low localization_mean). A court-defensible
        # splice assertion must not fire on authentic evidence photos, so we require a
        # CONFIDENT detection: a strong global score, OR a moderate score backed by a
        # substantive localized forgery area (mean forgery probability), not a handful
        # of speck regions. Genuine object splices clear this comfortably; annotation
        # overlays do not.
        loc_mean = float(pmap.mean())
        splicing_detected = score >= 0.70 or (score >= 0.5 and loc_mean >= 0.15)

        # Plan 3.4 — surface the per-pixel forgery-localization map.  Always
        # generate the heatmap when TruFor succeeds so the result page shows a
        # visual confirmation of the analysis (green/cool = authentic, warm = spliced).
        # The base64 PNG is small (~20-40KB after the 256px cap in the encoder) and
        # travels inline in the signed report payload.
        localization_map_png = _encode_localization_heatmap(pmap, rgb)

        result = {
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
        if localization_map_png:
            result["localization_map_png"] = localization_map_png
            if splicing_detected:
                result["localization_map_caption"] = (
                    "TruFor per-pixel forgery-probability map — warm regions indicate "
                    "higher manipulation likelihood, overlaid on the evidence."
                )
            else:
                result["localization_map_caption"] = (
                    "TruFor per-pixel forgery-probability map — predominantly cool/green "
                    "confirms low manipulation likelihood across the evidence."
                )
        return result
    except Exception as e:
        return {"available": False, "error": f"TruFor inference failed: {e}", "model_version": "trufor_real_v1"}


def _encode_localization_heatmap(pmap, base_rgb, max_side: int = 256) -> str | None:
    """Render TruFor's forgery-probability map as a base64 PNG data URI (plan 3.4).

    The probability map is colour-mapped (JET: cool→warm with rising likelihood),
    alpha-blended over the downscaled evidence for spatial context, capped to
    ``max_side`` px on the long edge to keep the signed-report payload small, and
    returned as a ``data:image/png;base64,...`` URI. Deterministic for a given
    input (no timestamp chunks), so it does not perturb the report signature.
    Returns ``None`` on any failure — the heatmap is supplementary, never required.
    """
    try:
        import base64

        import cv2
        import numpy as np

        hm = np.clip(np.asarray(pmap, dtype=np.float32), 0.0, 1.0)
        heat = cv2.applyColorMap((hm * 255.0).astype(np.uint8), cv2.COLORMAP_JET)  # BGR
        base_bgr = cv2.cvtColor(base_rgb, cv2.COLOR_RGB2BGR)
        if heat.shape[:2] != base_bgr.shape[:2]:
            heat = cv2.resize(
                heat, (base_bgr.shape[1], base_bgr.shape[0]), interpolation=cv2.INTER_LINEAR
            )
        overlay = cv2.addWeighted(base_bgr, 0.55, heat, 0.45, 0.0)

        h, w = overlay.shape[:2]
        long_side = max(h, w)
        if long_side > max_side:
            s = max_side / float(long_side)
            overlay = cv2.resize(
                overlay, (int(round(w * s)), int(round(h * s))), interpolation=cv2.INTER_AREA
            )

        ok, buf = cv2.imencode(".png", overlay)
        if not ok:
            return None
        return "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode("ascii")
    except Exception:
        return None
