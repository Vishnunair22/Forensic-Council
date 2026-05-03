# Model Licensing Reference

This file documents ML model licensing for the Forensic Council system. For detailed information, see [MODELS.md](MODELS.md).

Last updated: 2026-04-25 | Status: v1.7.0

---

## Quick Reference

| Model | License | Commercial Use |
|-------|---------|---------------|
| YOLO (Ultralytics) | AGPL-3.0 | Requires source disclosure |
| OpenCLIP (ViT-B-32) | MIT | No restrictions |
| AST Anti-Spoofing | Apache-2.0 | No restrictions |
| AASIST (opt-in) | Research-only | NOT cleared for production |
| pyannote | MIT | Requires HF account acceptance |
| Gemini 2.5 Flash | API ToS | Review data retention policy |
| Llama 3.3 70B | Meta Llama 3 | Under 700M MAU |
| wav2vec2 deepfake (Vansh180/...) | HuggingFace Hub | Check model's license tag |

---

## Vansh180/deepfake-audio-wav2vec2

This model (used by Agent 2 as the primary audio deepfake detector) requires license verification:

```bash
# Check the model card for license details
huggingface-cli download Vansh180/deepfake-audio-wav2vec2 --local-dir /tmp/model-check
# Or inspect the model card online at:
# https://huggingface.co/Vansh180/deepfake-audio-wav2vec2
```

If the model lacks a commercial-use license, the system will fall back to heuristic MFCC analysis.

---

## Required Actions Before Production

- [ ] Legal sign-off on AGPL (YOLO) — confirm deployment doesn't constitute distribution
- [ ] Remove research-only models if commercial/forensic use
- [ ] Confirm Gemini API data handling compatible with evidence obligations
- [ ] Accept pyannote terms via HuggingFace account

---

For full details, see [MODELS.md](MODELS.md).