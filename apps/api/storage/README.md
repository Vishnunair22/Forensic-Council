# Storage Root

This directory (`apps/api/storage/`) is the canonical storage root for all runtime artifacts of the Forensic Council application:

- `evidence/`: Holds incoming and analyzed evidence files (images, audio, video).
- `calibration_models/`: Holds local calibration model files.
- `keys/`: Holds cryptographic keys (if stored locally).

All root-level storage paths are ignored via `.gitignore` except for `.gitkeep` placeholder files. The root `/storage/` folder has been deleted and must not be used to prevent data leakage and ensure proper chain-of-custody containment.
