# Phase 03: Quality Audit & Cleanup - Validation Strategy

## Overview
This phase validates the code quality and test integrity of the Forensic Council backend.

## Success Criteria Mapping

| ID | Criterion | Verification Method |
|----|-----------|--------------------|
| QUAL-01 | Global Coverage >= 60% | `python -m pytest --cov=. --cov-fail-under=60` |
| QUAL-02 | OCR Tools Coverage >= 70% | `python -m pytest --cov=tools.ocr_tools --cov-report=term-missing` |
| QUAL-03 | Video Tools Coverage >= 70% | `python -m pytest --cov=tools.video_tools --cov-report=term-missing` |
| QUAL-04 | Auth RS256/AUD Enforcement | New tests in `tests/unit/test_auth_unit.py` |
| QUAL-05 | Linting & Type Integrity | `ruff check .` and `pyright .` exit 0 |

## Test Environment
- Python 3.12+ (uv)
- Pytest with `cov`, `asyncio`, `mock` plugins
- Mocked redis for working memory tests

## UAT Criteria
- [ ] User can run `pytest` and see 60%+ coverage.
- [ ] All 5 agents pass their individual unit tests.
- [ ] Auth rejects tokens without `aud` claim or signed with `HS256` after upgrade.
