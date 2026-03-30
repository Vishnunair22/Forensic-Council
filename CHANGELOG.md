# Changelog

All notable changes to Forensic Council are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.1.1] - 2026-03-30

### Security

- Removed exposed API keys from git history (`Locks and Keys.txt`, 13 PEM private keys)
- Replaced stub calibration model with explicit uncalibrated warnings in court statements
- Fixed silent chain-of-custody gaps — `log_entry()` now returns `None` on failure instead of a fake UUID
- Fixed module-level config capture in `auth.py` — JWT secrets now read dynamically via `get_settings()`
- Added production validation at startup — rejects demo credentials in production mode
- Hardened `.dockerignore` to exclude secrets from Docker build context
- Fixed `metadata_tools.py` bug where `file_created` used `st_mtime` instead of `st_ctime`

### Fixed

- EasyOCR Reader now reuses cached singleton from `ocr_tools.py` instead of re-instantiating ~100MB models per call
- ASGI upload size middleware now wraps `scope["receive"]` instead of patching `request._receive`
- Fixed `.env.example` bootstrap passwords — replaced `change-me-in-production` with explicit `SET_A_STRONG_PASSWORD_BEFORE_DEPLOYMENT`

### Changed

- Version aligned to 1.1.1 across `pyproject.toml` and `package.json`
- ESLint `max-warnings` reduced from 50 to 0
- TypeScript pinned to exact version `5.8.3`
- Extracted duplicated `fmtTool()` into `frontend/src/lib/fmtTool.ts`
- Extracted duplicated verdict config into `frontend/src/lib/verdict.ts`
- Extracted duplicated lossless detection into `backend/core/image_utils.py`

### Added

- GitHub Actions CI/CD pipeline (backend lint/test, frontend lint/build, security scan)
- `.editorconfig` for cross-editor consistency
- `validate_production_settings()` function in `config.py`
- This CHANGELOG

## [1.0.4] - 2026-03-16

### Fixed

- Session runtime audit: Report race-window, AttributeError in inter-agent calls
- Backend audit: 404 resume endpoint, Pydantic validation errors
- Frontend-backend connectivity: URL mappings verified
- Critical bugs: useRef lazy-init, react_loop missing agent_id, deep pass deduplication

### Security

- JWT 60-min expiry enforced
- Rate limiting: 10 investigations per 5-min window
- Redis/PostgreSQL hardening for production
- ECDSA P-256 report signing

## [1.0.0] - 2026-03-01

### Added

- Initial release: 5-agent forensic analysis system
- PostgreSQL chain-of-custody logging
- WebSocket real-time analysis streaming
- ECDSA-signed cryptographic reports
