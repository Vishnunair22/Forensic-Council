# Phase 1: Structural Audit & Fix — Research

**Researched:** 2026-04-16
**Domain:** Python FastAPI async refactoring — monolith decomposition
**Confidence:** HIGH

---

## Summary

Phase 1 targets four monolithic Python files totalling 9,096 lines that have mixed concerns, difficult unit-test isolation, and maintenance risk. All four files are deeply used by tests, orchestration, and the API layer, so every extraction must preserve the original module's public API via re-exports. No circular imports exist today; all proposed extractions move code strictly downward in the dependency tree (core → agents → orchestration → api), keeping that property intact.

The safest refactoring sequence is bottom-up: start with the leaf module (`react_loop.py`) because it has the most consumers and its Pydantic models are the widest-spread shared types. Work upward to `base_agent.py`, then `arbiter.py`, then `investigation.py`. Within each file, the safe extraction unit is any group of symbols that can be moved to a new sibling module with no forward references back to the original file.

The only confirmed import bug uncovered during research is in `apps/api/api/main.py` line 278: it imports `_active_tasks` from `api.routes.investigation`, but that symbol lives in `api.routes._session_state`. This must be fixed as part of STRUCT-07.

**Primary recommendation:** Extract in dependency order (react_loop → base_agent → arbiter → investigation), always maintain backward-compatible re-exports until all consumers are updated, and run `uv run pytest tests/unit/ -x` after each file extraction.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| STRUCT-01 | All monolithic files (>1000 lines with mixed concerns) decomposed into focused modules | Four files identified and mapped; safe extraction boundaries documented per file |
| STRUCT-02 | `investigation.py` route handler extracted — `run_investigation_task` and `instrumented_run` moved to `orchestration/investigation_runner.py` | Lines 538–2526 contain `_wrap_pipeline_with_broadcasts` and `run_investigation_task`; constants (`_EXACT_MIME_EXT_MAP`, phrase tables) belong in a separate constants module |
| STRUCT-03 | `react_loop.py` tool interpreters extracted to `core/tool_interpreters.py`; HITL logic extracted to `core/hitl.py` | `_TOOL_INTERPRETERS` dict is a local variable inside `_build_readable_summary` (lines 1881–2543); HITL methods are `check_hitl_triggers`, `pause_for_hitl`, `resume_from_hitl` at lines 1376–1536 |
| STRUCT-04 | `arbiter.py` split into verdict computation, narrative synthesis, and thin coordinator | `_calculate_manipulation_probability` is inline inside `deliberate()`; narrative methods are lines 1618–2299; data models are lines 31–169 |
| STRUCT-05 | `base_agent.py` self-reflection logic extracted to `agents/reflection.py` | `SelfReflectionReport` model (lines 42–71) and `_attach_llm_reasoning_to_findings` function (lines 74–199) are independent of `ForensicAgent` class |
| STRUCT-06 | Out-of-order definitions fixed (`_EXACT_MIME_EXT_MAP` and similar) | `_EXACT_MIME_EXT_MAP` defined at line 426 but referenced at line 284 in `start_investigation`; fix by moving constant above line 134 |
| STRUCT-07 | Import conventions enforced throughout codebase (no legacy `infra.persistence` imports) | Zero `infra.persistence` imports found in codebase (already clean); but one stale import found: `main.py:278` imports `_active_tasks` from `investigation` instead of `_session_state` |
| STRUCT-08 | All circular imports or import-time side effects resolved | No circular imports detected; one import-time side effect: `_tracer = get_tracer(...)` at module level in `react_loop.py` — safe, but should be noted |
</phase_requirements>

---

## Standard Stack

### Core (No New Dependencies Needed)

This phase is purely structural refactoring. No new libraries are required. All tools are already present in the project.

| Tool | Version | Purpose | Notes |
|------|---------|---------|-------|
| Python | 3.12 | Runtime | [VERIFIED: pyproject.toml] |
| FastAPI | >=0.115.12 | Route framework | [VERIFIED: pyproject.toml] |
| Pydantic v2 | >=2.11 | Data models | [VERIFIED: pyproject.toml] |
| uv | 0.6.5 | Package manager | [VERIFIED: STACK.md] |
| ruff | >=0.9 | Linting post-refactor | [VERIFIED: pyproject.toml] |
| pyright | 1.1.400 | Type checking post-refactor | [VERIFIED: pyproject.toml] |
| pytest + pytest-asyncio | >=8.4 + >=1.0 | Test runner | [VERIFIED: pyproject.toml] |

**Test run command:**
```bash
cd apps/api && uv run pytest tests/unit/ -x -q
```

**Full suite:**
```bash
cd apps/api && uv run pytest tests/ -x -q
```

---

## Architecture Patterns

### Dependency Graph (Current)

```
api/routes/investigation.py
    └── orchestration/pipeline.py
            ├── agents/arbiter.py
            │       └── (data models shared with core/)
            ├── agents/base_agent.py (via ForensicAgent)
            │       └── core/react_loop.py
            │               ├── core/custody_logger.py
            │               ├── core/llm_client.py
            │               ├── core/tool_registry.py
            │               └── core/working_memory.py
            └── core/react_loop.py (AgentFinding, HumanDecision)
```

The dependency tree flows strictly downward. No circular imports exist. [VERIFIED: grep audit of all imports]

### Safe Refactoring Sequence

**Rule:** Extract from the bottom of the tree first. Never create a new import that points upward in the graph above.

```
Step 1: core/react_loop.py  →  core/hitl.py + core/tool_interpreters.py
Step 2: agents/base_agent.py  →  agents/reflection.py
Step 3: agents/arbiter.py  →  agents/arbiter_verdict.py + agents/arbiter_narrative.py
Step 4: api/routes/investigation.py  →  orchestration/investigation_runner.py + api/constants.py
Step 5: Fix import convention bug in api/main.py
Step 6: Fix out-of-order definition (_EXACT_MIME_EXT_MAP)
```

### Pattern: Re-Export to Maintain Backward Compatibility

When extracting symbols from a module, keep the original module importable for all existing consumers by re-exporting from it. This is mandatory because tests, orchestration, and other files import from the original paths.

```python
# In core/react_loop.py — after extracting to core/hitl.py:
from core.hitl import (        # re-export — consumers unchanged
    HITLCheckpointReason,
    HITLCheckpointState,
    HITLCheckpointStatus,
    HumanDecision,
    HumanDecisionType,
)
```

Tests import `from core.react_loop import HumanDecision`, `AgentFinding`, `ReActLoopEngine`, `HITLCheckpointReason`, `HITLCheckpointState`, `ReActLoopResult`, `create_llm_step_generator`, `parse_llm_step`, `_build_forensic_system_prompt`, `_get_available_tools_for_llm`. All must remain importable from `core.react_loop`. [VERIFIED: grep of all test imports]

### Pattern: Module-Level Re-Export for Agents Package

`agents/__init__.py` currently re-exports `ForensicAgent` and `SelfReflectionReport` from `agents.base_agent`. After extracting `SelfReflectionReport` to `agents/reflection.py`, update both `base_agent.py` (re-export from reflection) and `agents/__init__.py` (import from new location or keep via base_agent chain). [VERIFIED: agents/__init__.py lines 12-17]

### Recommended Project Structure (Post-Refactor)

```
apps/api/
├── api/
│   ├── routes/
│   │   ├── investigation.py      # thin route handler (<200 lines)
│   │   ├── _session_state.py     # unchanged (already extracted)
│   │   └── _rate_limiting.py     # unchanged (already extracted)
│   └── constants.py              # NEW: MIME maps, phrase tables
├── agents/
│   ├── base_agent.py             # ForensicAgent ABC + ForensicAgent lifecycle
│   ├── reflection.py             # NEW: SelfReflectionReport + _attach_llm_reasoning
│   ├── arbiter.py                # thin coordinator (<400 lines)
│   ├── arbiter_verdict.py        # NEW: _TOOL_RELIABILITY_TIERS, probability calc
│   └── arbiter_narrative.py      # NEW: LLM narrative synthesis methods
├── core/
│   ├── react_loop.py             # ReActLoopEngine + re-exports
│   ├── hitl.py                   # NEW: HITL models + ReActLoopEngine HITL methods
│   └── tool_interpreters.py      # NEW: _TOOL_INTERPRETERS dict as module constant
└── orchestration/
    ├── pipeline.py               # unchanged
    └── investigation_runner.py   # NEW: run_investigation_task, _wrap_pipeline_with_broadcasts
```

### Anti-Patterns to Avoid

- **Moving without re-exporting:** Any extraction that removes a symbol from its current import path without re-exporting it will break existing tests and callers immediately. Always re-export first, migrate callers second.
- **Extracting a local variable dict as a module constant with the same behavior:** `_TOOL_INTERPRETERS` is currently a `dict` local variable inside `_build_readable_summary`. When moved to `core/tool_interpreters.py`, it becomes a module-level constant (allocated once at import time rather than per-call). This is a performance improvement and safe because the dict is stateless.
- **Extracting methods that hold `self` references:** HITL methods (`check_hitl_triggers`, `pause_for_hitl`, `resume_from_hitl`) use `self` heavily. They cannot be cleanly extracted as standalone functions without the `ReActLoopEngine` `self` reference. The correct extraction is as a mixin class or as module-level functions that receive the engine state as parameters. The simplest safe approach is to leave them as methods on `ReActLoopEngine` but move the HITL Pydantic *models* and *enums* to `core/hitl.py`.
- **Modifying arbiter verdict logic during refactor:** CLAUDE.md explicitly warns: "Never modify Arbiter verdict logic without understanding." The probability formula and `_TOOL_RELIABILITY_TIERS` must be moved verbatim, not rewritten.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Re-exports | Custom module shims | Python `from module import X; __all__` pattern | Native, zero overhead |
| Import order fixing | Custom import rewriter | Ruff isort (`ruff check --select I`) | Already configured |
| File line count verification | Manual counting | `wc -l` (in success criteria) | Used in phase success criteria |
| Test isolation for async code | Custom test fixtures | pytest-asyncio with `asyncio_mode = "auto"` | Already configured in pyproject.toml |

---

## File-by-File Extraction Map

### STRUCT-01 / STRUCT-03: `core/react_loop.py` (2,617 lines)

**What stays in react_loop.py:**
- `ReActStepType`, `ReActStep` (models, lines 33–60) — core loop step types
- `ReActLoopResult` (model, line 218) — loop result type
- `AgentFindingStatus`, `AgentFinding` (models, lines 135–216) — finding types
- `ReActLoopEngine` class (line 632 onward) — the loop engine itself including HITL methods
- `create_llm_step_generator`, `_build_forensic_system_prompt`, `_get_available_tools_for_llm` (lines 247–631) — LLM driver helpers
- Module-level re-exports from extracted modules

**What moves to `core/hitl.py` (new file):**
- `HITLCheckpointReason` enum (lines 62–69)
- `HITLCheckpointStatus` enum (lines 72–79)
- `HITLCheckpointState` model (lines 81–107)
- `HumanDecisionType` enum (lines 109–116)
- `HumanDecision` model (lines 119–132)

Note: `check_hitl_triggers`, `pause_for_hitl`, `resume_from_hitl` methods remain on `ReActLoopEngine` because they use `self` (working memory, session_id, custody_logger, redis_client, agent_id). They import HITL types from the new `core/hitl.py`.

**What moves to `core/tool_interpreters.py` (new file):**
- The `_TOOL_INTERPRETERS` dict (currently a local variable, lines 1881–2543) promoted to module-level constant `TOOL_INTERPRETERS`
- The function `_build_readable_summary` signature changes: replace inline dict with call to `TOOL_INTERPRETERS` from the new module

Estimated post-refactor size of `react_loop.py`: ~2,000 lines (HITL models move out, ~140 lines; interpreter dict stays functionally equivalent but as a module constant import). The engine itself is large. The STRUCT-03 requirement says "tool interpreters extracted to `core/tool_interpreters.py`" — this is the priority extraction, along with HITL models.

**Consumers of `core/react_loop` that require re-exports:** [VERIFIED: grep audit]
- `agents/base_agent.py`: `AgentFinding`, `HITLCheckpointReason`, `ReActLoopEngine`, `create_llm_step_generator`
- `api/routes/hitl.py`: `HumanDecision`
- `core/grounding.py`: `AgentFinding`
- `core/synthesis.py`: `AgentFinding`
- `orchestration/pipeline.py`: `AgentFinding`, `HumanDecision`
- `tests/unit/test_react_loop.py`: `AgentFinding`, `HITLCheckpointReason`, `HITLCheckpointState`, `HumanDecision`, `HumanDecisionType`, `ReActStep`, `ReActStepType`
- `tests/unit/test_react_loop_engine.py`: `AgentFinding`, `AgentFindingStatus`, `HITLCheckpointReason`, `HITLCheckpointState`, `HumanDecision`, `ReActLoopEngine`, `ReActLoopResult`, `create_llm_step_generator`, `parse_llm_step` — plus `_build_forensic_system_prompt` and `_get_available_tools_for_llm` via local import

---

### STRUCT-01 / STRUCT-05: `agents/base_agent.py` (1,601 lines)

**What stays in base_agent.py:**
- `ForensicAgent` ABC (line 200 onward) — the full abstract base class
- Module-level re-exports from extracted modules

**What moves to `agents/reflection.py` (new file):**
- `SelfReflectionReport` model (lines 42–71)
- `_attach_llm_reasoning_to_findings` function (lines 74–199)
- The `self_reflection_pass` method, `_get_evidence_context_for_reflection`, `_check_untreated_absences`, `_check_deprioritized_avenues` — these use `self` so they stay on `ForensicAgent`, but they import `SelfReflectionReport` from `agents/reflection.py`

Estimated post-refactor size of `base_agent.py`: ~1,440 lines (160 lines move). Still large but focused on the `ForensicAgent` lifecycle.

**Consumers requiring re-exports:** [VERIFIED: grep audit]
- `agents/__init__.py`: `ForensicAgent`, `SelfReflectionReport`
- `tests/unit/test_agents.py`: `SelfReflectionReport`
- `tests/unit/test_base_agent_functions.py`: `ForensicAgent`, `_attach_llm_reasoning_to_findings`

---

### STRUCT-01 / STRUCT-04: `agents/arbiter.py` (2,352 lines)

**What stays in arbiter.py (thin coordinator):**
- `CouncilArbiter.__init__` and `CouncilArbiter.deliberate` (coordinator logic ~350 lines)
- Re-exports of all data models and sub-modules
- `cross_agent_comparison`, `challenge_loop`, `trigger_tribunal`, `sign_report` (orchestration methods)

**What moves to `agents/arbiter_verdict.py` (new file):**
- `FindingVerdict`, `FindingComparison`, `ChallengeResult`, `TribunalCase`, `AgentMetrics`, `ForensicReport` — data models (lines 31–169)
- `_TOOL_RELIABILITY_TIERS` dict (lines 293–338) — move as class variable to a standalone function or module constant
- `_SINGLE_SIGNAL_DECAY`, `_MANIP_PROBABILITY_CAP` constants (lines 348–349)
- `_FINDING_CATEGORY_MAP`, `_AGENT_NAMES` class variables (lines 200–292)
- The manipulation probability calculation logic (inline in `deliberate()`, lines ~930–1070) — extract as `calculate_manipulation_probability(findings, ...) -> float` standalone function

**What moves to `agents/arbiter_narrative.py` (new file):**
- `_generate_agent_narrative` (lines 1618–1799)
- `_generate_executive_summary`, `_llm_executive_summary`, `_template_executive_summary` (lines 1800–2006)
- `_generate_uncertainty_statement`, `_llm_uncertainty_statement` (lines 2007–2060)
- `_generate_structured_summary`, `_llm_structured_summary`, `_template_structured_summary`, `_template_uncertainty_statement` (lines 2061–2299)
- `render_text_report` function (lines 2300–2352)

**Important:** All these narrative methods use `self` (access `self.config`, `self._synthesis_client`, `self.session_id`). The cleanest approach is to keep them as methods on `CouncilArbiter` but move their definitions into `arbiter_narrative.py` using a mixin pattern, or to move them to module-level async functions that receive the required parameters explicitly. The simpler approach — per CLAUDE.md "never modify Arbiter verdict logic without understanding" — is to move the narrative methods as a `ArbiterNarrativeMixin` class that `CouncilArbiter` inherits from.

**Consumers requiring re-exports:** [VERIFIED: grep audit]
- `orchestration/pipeline.py`: `CouncilArbiter`, `ForensicReport`
- `reports/report_renderer.py`: `ForensicReport`, `render_text_report`
- `tests/unit/test_arbiter_unit.py`: `AgentMetrics`, `ChallengeResult`, `CouncilArbiter`, `FindingComparison`, `FindingVerdict`, `ForensicReport`, `TribunalCase`
- `tests/unit/test_arbiter_full.py`: same set
- `tests/unit/test_arbiter_smoke.py`: `CouncilArbiter`, `ForensicReport`

---

### STRUCT-01 / STRUCT-02 / STRUCT-06: `api/routes/investigation.py` (2,526 lines)

**What stays in investigation.py (thin route handler):**
- `start_investigation` route handler and its validation helpers (lines 62–421)
- `ALLOWED_MIME_TYPES`, `MAX_FILE_SIZE`, `_ALLOWED_EXTENSIONS`, `_SAFE_ID_RE` constants (lines 69–113)
- `router` definition (line 67)
- WebSocket route handler (if any)
- Re-exports from extracted modules

**What moves to `orchestration/investigation_runner.py` (new file):**
- `run_investigation_task` async function (lines 2236–2526)
- `_wrap_pipeline_with_broadcasts` async function (lines 538–2235) — the large orchestration closure

**What moves to `api/constants.py` (new file):**
- `_EXACT_MIME_EXT_MAP` dict (lines 426–441) — also fixes STRUCT-06 out-of-order issue
- `_PIPELINE_TASK_PHRASES` dict (lines 446–537)
- `_TICKER_PHRASES` and `_DEEP_TICKER_PHRASES` (currently local variables inside `_wrap_pipeline_with_broadcasts`, lines 1506 and 2136) — promote to module-level constants

**STRUCT-06 fix:** Move `_EXACT_MIME_EXT_MAP` from line 426 to before `start_investigation` at line 134. The comment at line 271 already says "defined at module level above." [VERIFIED: investigation.py lines 271, 284, 426]

**STRUCT-07 import bug fix:** `api/main.py` line 278 does `from api.routes.investigation import _active_tasks`, but `_active_tasks` is defined in `api/routes/_session_state.py`. Fix: change import to `from api.routes._session_state import _active_tasks`. [VERIFIED: _session_state.py line 51, main.py line 278]

**Consumers:** `api/main.py` imports `investigation` module directly (`from api.routes import ... investigation`) and calls `investigation.cleanup_connections()` — this is actually `_session_state.cleanup_connections` accessed via `investigation` module alias; after refactor, `investigation.py` must still expose `cleanup_connections` via re-export or main.py must be updated. [VERIFIED: main.py lines 24, 313]

---

## Common Pitfalls

### Pitfall 1: Breaking Test Imports by Moving Without Re-Exporting

**What goes wrong:** A symbol is moved to a new module. All existing `from core.react_loop import HITLCheckpointState` statements break with `ImportError`.
**Why it happens:** Python imports are path-specific; moving a class changes its canonical path.
**How to avoid:** In the original module, add `from core.hitl import HITLCheckpointState` after the extraction. This re-export makes the old import path still work. Only remove the re-export after all consumers are updated.
**Warning signs:** `ImportError` in unit tests immediately after moving a file.

### Pitfall 2: Extracting `self`-Bound Methods to Standalone Functions

**What goes wrong:** A method like `_generate_agent_narrative(self, agent_id, findings)` is moved to a module-level function `generate_agent_narrative(agent_id, findings)`. All the `self.config`, `self._synthesis_client`, `self.session_id` references break.
**Why it happens:** Python methods rely on `self` for state; moving to a function loses the implicit state binding.
**How to avoid:** For narrative methods in `arbiter.py`, use a mixin class. For `_build_readable_summary` in `react_loop.py`, pass the tool registry state as arguments. For HITL Pydantic models, they have no `self` dependency — extraction is clean.
**Warning signs:** `AttributeError: 'NoneType' object has no attribute 'config'` at test time.

### Pitfall 3: Moving `_TOOL_INTERPRETERS` Local Dict to Module Level Incorrectly

**What goes wrong:** `_TOOL_INTERPRETERS` is currently a local variable inside `_build_readable_summary`. If extracted to module level, calls like `interpreter(output)` still work, but the dict is rebuilt on every import rather than every call — this is the desired behavior, not a bug. However, if the extraction changes the lambda parameter signatures (e.g., `o` → `output`), the lambdas silently produce wrong output.
**Why it happens:** Lambda parameters are positional; renaming them changes nothing functionally but may cause confusion.
**How to avoid:** Move dict verbatim. Do not rename lambda parameters.
**Warning signs:** Incorrect observation summaries in agent cards (UI regression); no immediate crash.

### Pitfall 4: Arbiter `deliberate()` Inline Logic is Not a Standalone Function

**What goes wrong:** The manipulation probability calculation is 100+ lines of inline code inside `deliberate()`, not a separate method. Attempting to extract it as a standalone function requires passing a large number of local variables as parameters.
**Why it happens:** The logic evolved inline and accumulated closures over local `dict`s.
**How to avoid:** Extract as `CouncilArbiter._calculate_manipulation_probability(self, active_findings, compression_penalty)` method first (remains on the class), then move to `arbiter_verdict.py` as a method on a `VerdictMixin`. Do not attempt to extract as a pure standalone function in one step.
**Warning signs:** `NameError` for variables like `_diffusion_detected_globally` or `compression_penalty` that were local to `deliberate()`.

### Pitfall 5: The `main.py` Graceful Shutdown Import Bug

**What goes wrong:** `api/main.py` line 278 imports `_active_tasks` from `api.routes.investigation`. That symbol does not exist in `investigation.py` — it is in `api.routes._session_state`. This currently fails silently because `investigation.py` imports `_active_pipelines` and `_final_reports` from `_session_state` at module load, and Python's module system may make the underlying dict accessible via the investigation namespace in some environments. But it is not guaranteed.
**How to avoid:** Fix to `from api.routes._session_state import _active_tasks` in `main.py`.
**Warning signs:** `ImportError` or `AttributeError` during graceful shutdown in certain Python/OS environments.

### Pitfall 6: Out-of-Order `_EXACT_MIME_EXT_MAP` Causes Future `NameError`

**What goes wrong:** The dict is at line 426 but referenced at line 284. Python resolves names at call time (not import time) for function bodies, so it currently works. But if any code between lines 270 and 426 ever references the constant at import time (e.g., in a class body or a module-level expression), a `NameError` will occur.
**How to avoid:** Move `_EXACT_MIME_EXT_MAP` to before `start_investigation` (line ~128), immediately after the other constants. This is a one-line move of a dict literal. [VERIFIED: investigation.py structure audit]

---

## Code Examples

### Pattern: Re-Export from Original Module

```python
# Source: Python language reference — __all__ and re-export conventions [ASSUMED pattern]
# In core/react_loop.py — after extraction:
from core.hitl import (
    HITLCheckpointReason,
    HITLCheckpointStatus,
    HITLCheckpointState,
    HumanDecisionType,
    HumanDecision,
)

# Re-export so existing consumers don't break
__all__ = [
    "HITLCheckpointReason",
    "HITLCheckpointState",
    "HITLCheckpointStatus",
    "HumanDecision",
    "HumanDecisionType",
    # ... existing symbols
]
```

### Pattern: Mixin for Arbiter Narrative Methods

```python
# Source: Python OOP best practices [ASSUMED pattern]
# In agents/arbiter_narrative.py:
class ArbiterNarrativeMixin:
    """LLM narrative synthesis methods for CouncilArbiter."""

    async def _generate_agent_narrative(
        self, agent_id: str, findings: list[dict], ...
    ) -> str:
        # Full body of current method — verbatim move

# In agents/arbiter.py:
from agents.arbiter_narrative import ArbiterNarrativeMixin
from agents.arbiter_verdict import (
    FindingVerdict, FindingComparison, ChallengeResult,
    TribunalCase, AgentMetrics, ForensicReport,
)

class CouncilArbiter(ArbiterNarrativeMixin):
    ...  # thin coordinator + cross_agent_comparison + challenge_loop + sign_report
```

### Pattern: Module-Level TOOL_INTERPRETERS Constant

```python
# In core/tool_interpreters.py:
from typing import Any, Callable

# Promoted from local variable inside _build_readable_summary
TOOL_INTERPRETERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "ela_full_image": lambda o: (
        # ... verbatim from react_loop.py lines 1883-1913
    ),
    # ... all other interpreters verbatim
}
```

```python
# In core/react_loop.py — updated _build_readable_summary:
from core.tool_interpreters import TOOL_INTERPRETERS

def _build_readable_summary(self, tool_name, ...) -> str:
    ...
    interpreter = TOOL_INTERPRETERS.get(tool_name)  # was: _TOOL_INTERPRETERS.get(...)
    ...
```

### Pattern: Fix main.py Import Bug

```python
# In api/main.py line 278 — BEFORE (broken):
from api.routes.investigation import _active_tasks

# AFTER (correct):
from api.routes._session_state import _active_tasks
```

---

## Runtime State Inventory

> This phase is structural source-code refactoring only — no renames, no data migrations.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — refactoring does not change data schemas or keys | None |
| Live service config | None — no service config references module file names | None |
| OS-registered state | None | None |
| Secrets/env vars | None — no env var names change | None |
| Build artifacts | `.venv/` — already present; `uv sync` not needed unless deps change | None |

**Nothing found in any category** — verified by scope review. This phase moves Python source code only.

---

## Environment Availability

| Dependency | Required By | Available | Notes |
|------------|------------|-----------|-------|
| Python 3.12 | All refactoring | Yes | [VERIFIED: pyproject.toml, STACK.md] |
| uv 0.6.5 | `uv run pytest` | Yes | [VERIFIED: STACK.md] |
| pytest >=8.4 | Test validation after each extraction | Yes | [VERIFIED: pyproject.toml] |
| ruff >=0.9 | Post-refactor lint | Yes | [VERIFIED: pyproject.toml] |
| pyright 1.1.400 | Post-refactor type checking | Yes | [VERIFIED: pyproject.toml] |

No missing dependencies. All tools are in the existing venv.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.4+ with pytest-asyncio 1.0+ |
| Config file | `apps/api/pyproject.toml` `[tool.pytest.ini_options]` |
| asyncio_mode | `auto` (all async tests run without `@pytest.mark.asyncio`) |
| Quick run command | `cd apps/api && uv run pytest tests/unit/ -x -q` |
| Full suite command | `cd apps/api && uv run pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| STRUCT-01 | No file exceeds 800 lines | smoke | `wc -l apps/api/**/*.py \| awk '$1 > 800'` | N/A (shell) |
| STRUCT-02 | `run_investigation_task` in `investigation_runner.py` | integration | `uv run pytest tests/integration/test_investigation_start_flow.py -x` | Yes |
| STRUCT-03 | HITL models importable from `core.hitl`; interpreters from `core.tool_interpreters` | unit | `uv run pytest tests/unit/test_react_loop.py tests/unit/test_react_loop_engine.py -x` | Yes |
| STRUCT-04 | Arbiter data models importable from `agents.arbiter` | unit | `uv run pytest tests/unit/test_arbiter_unit.py tests/unit/test_arbiter_full.py -x` | Yes |
| STRUCT-05 | `SelfReflectionReport` importable from `agents.reflection` | unit | `uv run pytest tests/unit/test_agents.py tests/unit/test_base_agent_functions.py -x` | Yes |
| STRUCT-06 | `_EXACT_MIME_EXT_MAP` before `start_investigation` | smoke | `grep -n "_EXACT_MIME_EXT_MAP" apps/api/api/routes/investigation.py \| head -1` output < line 134 | N/A (grep) |
| STRUCT-07 | No legacy `infra.` imports; `main.py` uses correct `_session_state` path | smoke | `grep -r "from infra\." apps/api/ --include="*.py"` returns empty | N/A (grep) |
| STRUCT-08 | No circular imports | smoke | `uv run python -c "import api.main"` exits 0 | N/A |

### Sampling Rate

- **Per extraction step:** `uv run pytest tests/unit/ -x -q` — must pass before next extraction
- **Per wave merge:** `uv run pytest tests/ -x -q` — full suite including integration tests
- **Phase gate:** `uv run ruff check .` + `uv run pyright .` + full test suite green

### Wave 0 Gaps

No new test files are needed. All extraction is protected by existing tests that verify:
- All public symbols remain importable from their original paths (import tests)
- Functional behavior is unchanged (unit and integration tests)

However, the following test gap is noted for awareness (not Wave 0 blocker):
- No unit test specifically asserts `run_investigation_task` is importable from `orchestration.investigation_runner` — the integration test `test_investigation_start_flow.py` tests the behavior but via `investigation_routes` monkeypatch. Post-refactor, a smoke import test should be added.

---

## Security Domain

> STRUCT-01 through STRUCT-08 are structural refactoring tasks. No security-sensitive code is being changed in behavior — only moved between files. The security concerns from CONCERNS.md (JWT `aud` validation, HS256 algorithm) are scoped to Phase 2 (FUNC-01, FUNC-02) and must NOT be modified during Phase 1.

| ASVS Category | Applies | Note |
|---------------|---------|------|
| V2 Authentication | No | Auth code not touched in Phase 1 |
| V5 Input Validation | Structural only | `_EXACT_MIME_EXT_MAP` move does not change validation logic |
| V6 Cryptography | No | Signing code not touched |

**Critical constraint:** Do not modify `auth.py` or `signing.py` during Phase 1. Those files contain known security issues deliberately left for Phase 2.

---

## Open Questions

1. **Arbiter narrative methods and `self` coupling**
   - What we know: Narrative methods use `self.config`, `self._synthesis_client`, `self.session_id`, `self.custody_logger`
   - What's unclear: Whether mixin pattern or parameter-passing pattern is preferred
   - Recommendation: Use mixin. It requires no interface change and is zero-risk. `CouncilArbiter(ArbiterNarrativeMixin)` is a one-line change.

2. **`investigation.py` `_wrap_pipeline_with_broadcasts` — local ticker phrase tables**
   - What we know: `_TICKER_PHRASES` and `_DEEP_TICKER_PHRASES` are local variables inside `_wrap_pipeline_with_broadcasts` at lines 1506 and 2136
   - What's unclear: Whether they should be constants in `api/constants.py` or parameters passed in
   - Recommendation: Move to `api/constants.py` as module-level constants. They are pure data (no logic), and making them module-level removes the only remaining reason `_wrap_pipeline_with_broadcasts` needs to be so large.

3. **Line count after extraction**
   - What we know: The goal is no file exceeds 800 lines; `base_agent.py` after extracting `SelfReflectionReport` (~160 lines) will still be ~1,440 lines
   - What's unclear: Whether further extraction from `base_agent.py` is needed to meet the 800-line target
   - Recommendation: `base_agent.py` likely still exceeds 800 lines after STRUCT-05. STRUCT-01 says "mixed concerns" is the criterion — the remaining code in `base_agent.py` is all `ForensicAgent` lifecycle. The success criterion says "no file exceeds 800 lines" generally. The planner should account for this and may need additional extraction tasks (e.g., episodic memory methods, inter-agent call handling).

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Mixin pattern for arbiter narrative is the safest refactoring approach | Architecture Patterns | Medium — if mixin creates MRO issues, use module-level functions with explicit params instead |
| A2 | `_active_tasks` import from `investigation` in `main.py` is a bug (not intentional re-export) | STRUCT-07 | Low — investigation.py clearly does not import or define `_active_tasks`; the symbol is only in `_session_state.py` |
| A3 | `base_agent.py` will still exceed 800 lines after STRUCT-05 extraction | Open Questions | Medium — planner must include additional extraction tasks if 800-line target is required for base_agent.py specifically |
| A4 | No `infra.persistence` legacy imports remain (STRUCT-07 partial) | Code audit | Low — grep confirmed zero occurrences across entire `apps/api/` tree |

---

## Sources

### Primary (HIGH confidence)
- `apps/api/api/routes/investigation.py` — direct read, line-count verified [VERIFIED: codebase grep]
- `apps/api/core/react_loop.py` — direct read, import graph verified [VERIFIED: codebase grep]
- `apps/api/agents/arbiter.py` — direct read, method locations verified [VERIFIED: codebase grep]
- `apps/api/agents/base_agent.py` — direct read, symbol locations verified [VERIFIED: codebase grep]
- `apps/api/api/routes/_session_state.py` — direct read, confirmed `_active_tasks` ownership [VERIFIED: codebase grep]
- `apps/api/api/main.py` — direct read, confirmed import bug at line 278 [VERIFIED: codebase grep]
- All test files under `apps/api/tests/unit/` and `apps/api/tests/integration/` — import audit [VERIFIED: grep of from-imports]
- `.planning/codebase/CONCERNS.md` — authoritative concern descriptions [VERIFIED: file read]

### Secondary (MEDIUM confidence)
- `apps/api/pyproject.toml` — pytest config, dependency versions [VERIFIED: file read]
- `.planning/codebase/ARCHITECTURE.md` — dependency graph description [VERIFIED: file read]

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all tools already present, no new dependencies
- Architecture: HIGH — full import graph verified via grep; no assumptions about dependency flow
- Extraction boundaries: HIGH — verified by reading actual file contents and line numbers
- Pitfalls: HIGH — all pitfalls derived from observed code structure, not hypothetical

**Research date:** 2026-04-16
**Valid until:** 2026-05-16 (stable codebase, no fast-moving deps)
