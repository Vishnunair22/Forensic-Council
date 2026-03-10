# Security Policy

The Forensic Council handles highly sensitive, evidentiary material. Security is our paramount concern.

## Cryptographic Signing Architecture

The system uses an ECDSA deterministic methodology to sign the final `InvestigationReport`.

### 1. The Signing Key
*   The system is seeded with a `SIGNING_KEY` 256-bit hexadecimal string defined in `.env`.
*   This key is used to derive an Elliptic Curve private key (SECP256R1 / P-256).

### 2. The Custody Chain
*   Upon the Council Arbiter reaching a final verdict, the entire JSON payload (including the verdict string, timestamp, and array of agent findings) is serialized.
*   This serialized string is hashed via **SHA-256** to generate the `report_hash`.
*   The `report_hash` is then signed using the derived private key. This signature is attached to the final DTO as `cryptographic_signature`.

### 3. Key Rotation Procedure
If the key must be rotated:
1.  Generate a new 32-byte hex.
2.  Update `SIGNING_KEY` in the `.env` root file.
3.  Restart the backend container: `docker compose -f docs/docker/docker-compose.yml --env-file .env up -d --force-recreate backend`
**Note:** Old reports accessed via the API or stored in Postgres will fail signature verification against the new key. This is expected and ensures temporal separation of evidence custody boundaries.

## Reporting a Vulnerability

If you discover a security vulnerability within the Forensic Council, please avoid opening a public issue.

Send an encrypted email directly to the project maintainers containing:
*   Description of the vulnerability.
*   The environment details (Docker version, Postgres/Redis versions).
*   A Proof-Of-Concept (PoC) script or detailed reproduction steps.

Maintainers will respond within 48 hours to acknowledge receipt and provide a triage timeline. 

**Vulnerability Types of High Interest:**
*   Bypass of file size validation checks.
*   Injection attacks via `case_id` or `investigator_id` payloads.
*   Any method capable of coercing an agent into an infinite ReAct loop, causing a Denial of Service (DoS) attack.
