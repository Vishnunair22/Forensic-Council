#!/usr/bin/env bash
#
# acquire_calibration_datasets.sh
# -------------------------------------------------------------------
# Fetches the calibration benchmarks named in docs/CALIBRATION.md and docs/CALIBRATION_RUNBOOK.md.
# RUN THIS INSIDE THE WORKER CONTAINER (ML models + real network),
# not in a sandbox with a restricted egress allowlist.
#
# Design:
#   * Per-agent functions, in the plan's recommended §6 order (1,3,2,4,5).
#   * Only the open / scriptable sets actually download.
#   * Gated sets (NIST MFC, FF++, DFDC, Celeb-DF v2) print the exact
#     registration steps — they require YOU to apply and accept an EULA.
#   * Nothing is adopted here. This only fetches raw data. Calibration
#     still goes through collect -> validate (gate) -> train, per the plan.
#
# Usage:
#   ./acquire_calibration_datasets.sh            # show plan + status, download nothing
#   ./acquire_calibration_datasets.sh agent1     # fetch Agent 1 (GenImage)
#   ./acquire_calibration_datasets.sh agent3     # fetch Agent 3 (CASIA) + NIST steps
#   ./acquire_calibration_datasets.sh agent2     # fetch Agent 2 (ASVspoof)
#   ./acquire_calibration_datasets.sh agent4     # print FF++/DFDC/Celeb-DF request steps
#   ./acquire_calibration_datasets.sh agent5     # fetch RAID (HuggingFace)
#   ./acquire_calibration_datasets.sh all        # everything scriptable, in order
#
# License acknowledgement: GenImage is CC BY-NC-SA 4.0 (NON-COMMERCIAL).
# Set CALIB_ACCEPT_LICENSES=1 to confirm you accept each set's terms.
# -------------------------------------------------------------------

set -euo pipefail

DATA_ROOT="${CALIB_DATA_ROOT:-/data}"
ACCEPT="${CALIB_ACCEPT_LICENSES:-0}"

c_bold=$'\033[1m'; c_red=$'\033[31m'; c_grn=$'\033[32m'; c_ylw=$'\033[33m'; c_off=$'\033[0m'
info()  { printf '%s[*]%s %s\n' "$c_grn" "$c_off" "$*"; }
warn()  { printf '%s[!]%s %s\n' "$c_ylw" "$c_off" "$*"; }
gate()  { printf '%s[GATED]%s %s\n' "$c_red" "$c_off" "$*"; }
hdr()   { printf '\n%s== %s ==%s\n' "$c_bold" "$*" "$c_off"; }

need() { command -v "$1" >/dev/null 2>&1 || { warn "missing tool: $1 ($2)"; return 1; }; }

accept_or_stop() {
  # $1 = dataset name, $2 = license summary
  if [[ "$ACCEPT" != "1" ]]; then
    warn "$1 is governed by: $2"
    warn "Re-run with CALIB_ACCEPT_LICENSES=1 once you've read and accept the terms."
    return 1
  fi
  info "License acknowledged for $1 ($2)"
}

# ------------------------------------------------------------------ #
# Agent 1 — GenImage (AI-generated images). Scriptable.
# ------------------------------------------------------------------ #
agent1_genimage() {
  hdr "Agent 1 — GenImage (AI-generated images)"
  accept_or_stop "GenImage" "CC BY-NC-SA 4.0 (NON-COMMERCIAL — confirm this fits your use)" || return 0
  local dst="$DATA_ROOT/genimage"; mkdir -p "$dst"
  info "Target: $dst   (expect ~real/ = ImageNet-1k val, ~ai/ = SD/MJ/ADM/GLIDE/Wukong/VQDM/BigGAN)"
  cat <<EOF
  Recommended source (easiest, de-biased mirror with metadata CSV):
    https://www.unbiased-genimage.org        # provides a ready download script
    https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/AKDIHF
  Canonical source (Baidu Yunpan, code ztf1 — slow outside Asia):
    https://genimage-dataset.github.io/  ·  repo: https://github.com/GenImage-Dataset/GenImage
  Supplement newer generators GenImage predates: Synthbuster, DRCT-2M.

  After download, lay out as the collector expects:
    $dst/real/   (authentic, label 0)
    $dst/ai/     (AI-generated, label 1; balance across generators)
EOF
  # The unbiased mirror ships its own downloader; clone it if present.
  if need git "clone the unbiased-genimage download helper"; then
    info "Tip: follow the per-generator download script on unbiased-genimage.org,"
    info "     then verify class balance before collecting scores."
  fi
}

# ------------------------------------------------------------------ #
# Agent 3 — CASIA v2 splicing (scriptable) + NIST MFC (registration).
# ------------------------------------------------------------------ #
agent3_splicing() {
  hdr "Agent 3 — Image splicing / tamper"
  local dst="$DATA_ROOT/splicing"; mkdir -p "$dst"
  info "Start with CASIA v2.0 (7,200 authentic + 5,123 spliced) — easiest access."
  cat <<EOF
  CASIA v2.0:  http://forensics.idealtest.org/
  Mirror index (verify labels match canonical): https://github.com/greatzh/Image-Forgery-Datasets-List
  Lay out as splice-vs-authentic PHOTOGRAPHS (your deployment domain, not faces-only):
    $dst/real/   (authentic photos, label 0)
    $dst/fake/   (spliced/forged, label 1)
EOF
  gate "NIST MFC2018 / MFC2019 (court-grade) — requires NIST registration:"
  cat <<EOF
    https://www.nist.gov/itl/iad/mig/media-forensics-challenge-2018
    https://mfc.nist.gov/
  Apply, agree to terms, cite the exact version alongside the persisted model
  in storage/calibration_models/Agent3/ for court-defensibility.
EOF
}

# ------------------------------------------------------------------ #
# Agent 2 — ASVspoof (synthetic / cloned voice). Scriptable (Zenodo).
# ------------------------------------------------------------------ #
agent2_asvspoof() {
  hdr "Agent 2 — ASVspoof (synthetic / cloned voice)"
  accept_or_stop "ASVspoof" "Open Data Commons Attribution (permissive, court-friendly)" || return 0
  local dst="$DATA_ROOT/asvspoof"; mkdir -p "$dst"
  info "Primary: ASVspoof 2021 DF (codec-processed, closest to deployment) + 2019 LA (clean TTS/VC)."
  cat <<EOF
  Zenodo record (2021):  https://zenodo.org/records/4835108
  Eval keys / meta-labels: https://www.asvspoof.org/index2021.html
EOF
  if need zenodo_get "pip install zenodo_get"; then
    info "Downloading Zenodo record 4835108 into $dst ..."
    ( cd "$dst" && zenodo_get 4835108 ) || warn "zenodo_get failed — fall back to manual download from the URL above."
  else
    warn "Install with: pip install zenodo_get   (then re-run agent2)"
  fi
  cat <<EOF
  Map to bona-fide vs spoof using the official protocol files:
    $dst/real/   (bona-fide, label 0)
    $dst/fake/   (TTS/VC spoof, label 1)
EOF
}

# ------------------------------------------------------------------ #
# Agent 4 — Video deepfake. ALL request-form gated.
# Also: needs a video collector runner before any data is usable.
# ------------------------------------------------------------------ #
agent4_video() {
  hdr "Agent 4 — Video deepfake"
  warn "BLOCKER (engineering, not data): collect_calibration_scores.py has no video runner."
  warn "Add one to the DETECTORS map (wrap interframe_forgery_detector or deepfake_frequency"
  warn "to emit a 0-1 score + _VIDEO_EXTS) BEFORE any of these datasets can produce a CSV."
  gate "FaceForensics++ (c23/c40) — request form / EULA:"
  echo  "    survey & links: https://www.mdpi.com/2079-9292/13/3/585"
  gate "DFDC — request form / EULA (professional actors, ~470GB; sample a balanced subset)."
  gate "Celeb-DF v2 — request form / EULA:"
  echo  "    overview: https://www.emergentmind.com/topics/celeb-df-dataset"
  warn "All three need lead time. Per §6, start the access requests NOW and build the"
  warn "video runner in parallel."
}

# ------------------------------------------------------------------ #
# Agent 5 — AI-text. RAID is scriptable, but NO local detector exists yet.
# ------------------------------------------------------------------ #
agent5_raid() {
  hdr "Agent 5 — AI-generated text (RAID)"
  warn "BLOCKER (engineering, not data): there is NO local AI-text detector."
  warn "Add one first (Binoculars / RADAR as a deployable open model, or a Gemini path),"
  warn "expose a score, wire it into the collector — THEN calibrate on RAID. Downloading now"
  warn "is fine for prep, but it can't be calibrated until the detector lands."
  local dst="$DATA_ROOT/raid"; mkdir -p "$dst"
  cat <<EOF
  RAID (ACL 2024): https://github.com/liamdugan/raid  ·  hf: liamdugan/raid
  Supplements: HC3 (Hello-SimpleAI/HC3), M4GT-Bench.
EOF
  if need python3 "load RAID via HuggingFace datasets"; then
    if python3 -c "import datasets" 2>/dev/null; then
      info "Fetching RAID via HuggingFace into the datasets cache ..."
      python3 - <<'PY' || warn "RAID fetch failed — ensure 'pip install datasets' and network to huggingface.co."
from datasets import load_dataset
ds = load_dataset("liamdugan/raid")
print("RAID splits:", list(ds.keys()))
PY
    else
      warn "Install with: pip install datasets   (then re-run agent5)"
    fi
  fi
}

print_overview() {
  cat <<EOF
${c_bold}Calibration dataset acquisition — status${c_off}
Data root: $DATA_ROOT   (override with CALIB_DATA_ROOT)
Licenses accepted: $([[ "$ACCEPT" == 1 ]] && echo yes || echo "no — set CALIB_ACCEPT_LICENSES=1")

  agent1  GenImage              scriptable    CC BY-NC-SA (non-commercial)
  agent3  CASIA v2 / NIST MFC   semi / GATED  CASIA open; NIST = registration
  agent2  ASVspoof 2021+2019    scriptable    Open Data Commons
  agent4  FF++ / DFDC / CelebDF GATED (EULA)  + needs video collector runner first
  agent5  RAID                  scriptable    + needs an AI-text detector first

Recommended order (plan §6):  agent1 -> agent3 -> agent2 -> agent4 -> agent5
After download, per agent run:  collect_calibration_scores.py -> validate_calibration.py (gate) -> train_calibration.py
Adopt ONLY on the gate's ADOPT verdict.
EOF
}

main() {
  local target="${1:-overview}"
  case "$target" in
    overview|"") print_overview ;;
    agent1) agent1_genimage ;;
    agent2) agent2_asvspoof ;;
    agent3) agent3_splicing ;;
    agent4) agent4_video ;;
    agent5) agent5_raid ;;
    all)
      print_overview
      agent1_genimage || true
      agent3_splicing || true
      agent2_asvspoof || true
      agent4_video    || true
      agent5_raid     || true
      ;;
    *) warn "unknown target: $target"; print_overview; exit 1 ;;
  esac
}

main "$@"
