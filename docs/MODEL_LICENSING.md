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

---

## Required Actions Before Production

- [ ] Legal sign-off on AGPL (YOLO) — confirm deployment doesn't constitute distribution
- [ ] Remove research-only models if commercial/forensic use
- [ ] Confirm Gemini API data handling compatible with evidence obligations
- [ ] Accept pyannote terms via HuggingFace account

---

For full details, see [MODELS.md](MODELS.md).