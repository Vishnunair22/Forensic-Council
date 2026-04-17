# Roadmap — Final Codebase Audit
**Created:** 2026-04-16
**Milestone:** v1.5.0 Final Polish

---

## Phase Overview

| # | Phase | Goal | Requirements | Status |
|---|-------|------|--------------|--------|
| 1 | Structural Check | Audit project for stray files, duplicates, and invalid paths | STR-01 to STR-04 | Completed |
| 2 | Logic Consolidation | Centralize thresholds and metadata-based compression risk | LOG-01 to LOG-03 | Completed |
| 3 | API Client & Polish | Hardened API client, partial validation, and structural polish | POL-01 to POL-03 | Completed |
| 4 | Base Class Decomposition | Refactor monolithic base agent into modular mixins | REF-01 to REF-02 | Completed |
| 5 | Docker Build Prep | Prepare app for fresh build with specific API keys and cache clearance | DOCK-01 to DOCK-04 | Completed |
| 6 | Docker Dev Build | Clean workspace and launch fresh development environment via Docker | DEV-01 to DEV-04 | Planned |

---

## Phase Details

### Phase 1: Structural Check
**Goal:** Ensure the project is lean, semantically organized, and path-valid.
**Requirements:** STR-01, STR-02, STR-03, STR-04
**Success Criteria:**
1. Zero stray or unwanted files in production trees.
2. 100% path validity across all config and source files.

### Phase 2: Logic Consolidation
**Goal:** Consolidate thresholds and extract metadata-based reliability risks.
**Requirements:** LOG-01, LOG-02, LOG-03

### Phase 3: API Client & Polish
**Goal:** Harden the frontend API client and finalize monorepo cleanliness.
**Requirements:** POL-01, POL-02, POL-03

### Phase 4: Base Class Decomposition
**Goal:** Modularize the monolithic `ForensicAgent` class.
**Requirements:** REF-01, REF-02

### Phase 5: Docker Build Prep
**Goal:** Prepare for a high-fidelity production build.
**Requirements:** DOCK-01, DOCK-02, DOCK-03, DOCK-04

### Phase 6: Docker Dev Build
**Goal:** Launch a clean, high-performance development workspace.
**Requirements:** DEV-01, DEV-02, DEV-03, DEV-04
