# ADR-005: Retain `_bcrypt_shim.py` Rather Than Migrate to Native bcrypt 4.x

**Status**: Accepted  
**Date**: 2026-05-10  
**Audit reference**: P2-API-002, audit v6→v7

---

## Context

`apps/api/core/_bcrypt_shim.py` exists because `passlib` 1.7.x calls private
`bcrypt` internals (`__about__.__version__` and the `_bcrypt_hashpw` name) that were
removed in `bcrypt` 4.0. Without the shim, importing `passlib.hash.bcrypt` raises
`AttributeError` at startup.

The shim patches those two attributes back onto the `bcrypt` module at import time,
allowing `passlib` to function with `bcrypt>=3.2,<4.1`.

---

## Decision

Retain the shim and the `bcrypt>=3.2,<4.1` pin.

**Rationale:**

1. **No CVE exposure.** The pinned range has no known security vulnerabilities as of
   this writing.
2. **Narrow blast radius.** The shim is a single 15-line file. It is covered by unit
   tests in `tests/security/`.
3. **Migration cost is disproportionate.** Removing passlib requires auditing every
   `CryptContext` / `hash.bcrypt.hash()` / `hash.bcrypt.verify()` call site across
   `core/auth.py` and related modules, updating password-hashing tests, and validating
   that existing password hashes stored in the database remain verifiable after the
   change. That work belongs in a dedicated story, not as a side-effect of an audit
   fix cycle.
4. **Forward compatibility is clear.** When the migration is prioritised:
   - Remove the shim file and `pyproject.toml` pin.
   - Replace `passlib.hash.bcrypt` with direct `bcrypt.hashpw` / `bcrypt.checkpw`
     calls.
   - Update `bcrypt` to `>=4.1`.

---

## Consequences

- `bcrypt` is pinned below 4.x indefinitely until the passlib migration is done.
- CI must continue to test the shim path.
- A future story should be opened to remove the shim when the passlib dependency is
  dropped or upgraded to a version that supports bcrypt 4.x natively.

---

## Alternatives Considered

**Remove shim, migrate to native bcrypt 4.x now.**  
Rejected for this audit cycle due to migration cost and the lack of any security
motivation (no CVE in the current pin).

**Pin passlib to a fork that supports bcrypt 4.x.**  
Rejected — introduces an unreviewed third-party fork with unknown maintenance status.
