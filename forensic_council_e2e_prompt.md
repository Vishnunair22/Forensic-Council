# Forensic Council — Full End-to-End Production Readiness Prompt
## For Claude Code / Codex / Agentic Executor

---

## MISSION STATEMENT

You are an expert senior engineer tasked with making **Forensic Council** — a multi-agent forensic media analysis platform — fully production-ready. Your mandate is to:

1. Run the app end-to-end as a real user would
2. Verify every feature works — with focus on **image analysis** (real-world photos AND digitally-created images)
3. Ensure every forensic tool fires cleanly and produces valid, substantive findings
4. Ensure initial analysis AND deep analysis both complete without errors
5. Ensure the final report is court-admissible, cryptographically signed, fully intact, and renders green
6. Fix **every** bug, stale file, config error, import error, and code-level issue found during any iteration
7. Eliminate all duplicate/stale/clutter files from the project
8. Ensure Docker dev mode uses **live code mounts** so no rebuild is needed on code changes
9. The deliverable is a project that someone can `git clone`, run `bash scripts/dev.sh`, and have a fully working forensic platform

**Iterate until the entire flow is clean. Do not stop at the first pass. Run at minimum 3 full end-to-end validation iterations.**

---

## STACK CONTEXT

- **Backend**: Python 3.12 / FastAPI / SQLAlchemy / Alembic — lives in `apps/api/`
- **Frontend**: Next.js 15 / React / TypeScript — lives in `apps/web/`
- **Infra**: Docker Compose, PostgreSQL, Redis, Qdrant, Caddy, Prometheus
- **AI/ML**: Groq (LLM synthesis), Google Gemini (vision), local ML models (YOLO/DETR, EasyOCR, TruFor, BusterNet, Noiseprint++, F3-Net, ManTra-Net, SigLIP2, ViT-ELA, CLIP, AASIST, wav2vec2)
- **Agents**: 5 specialist agents + CouncilArbiter with cryptographic signing
  - Agent 1: Pixel Integrity (image manipulation, AI-generation detection)
  - Agent 2: Audio Forensics
  - Agent 3: Object/Scene Detection
  - Agent 4: Video Temporal Analysis
  - Agent 5: Metadata/EXIF Forensics
  - Council Arbiter: cross-agent deliberation, tribunal, signed verdict
- **Report formats**: PDF (court export), DOCX (court export), in-app HTML verdict

---

## PHASE 0 — ENVIRONMENT SETUP & VERIFICATION

### 0.1 — Read all key files before touching anything

Read and internalize:
- `infra/docker-compose.yml` (base compose)
- `infra/docker-compose.dev.yml` (dev override — port exposure)
- `apps/api/Dockerfile` (multi-stage: base → deps-core → deps-full → migration → app → development → production)
- `apps/web/Dockerfile` (development → runner)
- `.env.example` (all required env vars)
- `scripts/dev.sh` (dev startup script)
- `apps/api/core/config.py` (Settings class — all env var names and types)
- `apps/api/api/main.py` (FastAPI app setup, lifespan, routers)
- `apps/api/agents/agent1_image.py` (primary focus agent)
- `apps/api/core/tool_names.py` (canonical tool name constants)
- `apps/api/core/handlers/image.py` (image tool implementations)
- `apps/api/core/react_loop.py` (agent execution engine)
- `apps/web/src/lib/api/client.ts` (frontend API client)

### 0.2 — Generate a valid `.env`

```bash
cp .env.example .env
bash infra/generate_production_keys.sh   # populates SIGNING_KEY, JWT_SECRET_KEY
```

Then set these values in `.env` (use real keys or valid dev stubs):
```
# Required secrets (generate_production_keys.sh handles these):
SIGNING_KEY=<generated>
JWT_SECRET_KEY=<generated>
POSTGRES_PASSWORD=forensic_dev_password_local
REDIS_PASSWORD=redis_dev_password_local
METRICS_SCRAPE_TOKEN=<generated or any 32-char string>

# LLM (set at least one):
LLM_PROVIDER=groq                          # or: none (for fully offline)
LLM_API_KEY=<your-groq-api-key>            # gsk_...
LLM_MODEL=llama-3.3-70b-versatile

# Vision (Gemini — optional but enables Agent1 deep pass):
GEMINI_API_KEY=<your-gemini-api-key>       # AIzaSy...
GEMINI_API_KEY_POLICY_OK=true              # REQUIRED — explicit opt-in
GEMINI_MODEL=gemini-2.5-flash
ANALYSIS_EXECUTION_MODE=hybrid             # hybrid enables Gemini; local_only for fully offline

# If no API keys available, use fully offline mode:
# LLM_PROVIDER=none
# ANALYSIS_EXECUTION_MODE=local_only
# OFFLINE_MODE=true
# GEMINI_API_KEY_POLICY_OK=false

# Worker
DOCKER_USE_REDIS_WORKER=true
```

**IMPORTANT**: `GEMINI_API_KEY_POLICY_OK` has NO default. It must be explicitly set to `true` or `false`. A missing value causes startup to fail with `ValidationError`. This is intentional (P0-SEC-001). Fix the `.env.example` to make this obvious if it is not already.

### 0.3 — Verify Docker version and BuildKit

```bash
docker --version          # must be 23+ for BuildKit default; or DOCKER_BUILDKIT=1
docker compose version    # must be v2 (compose as plugin, not docker-compose)
```

---

## PHASE 1 — DOCKER DEV MODE WITH LIVE CODE MOUNTS

### 1.1 — Audit the compose volume mounts for hot-reload

Open `infra/docker-compose.yml`. Locate the `backend` and `frontend` service definitions.

**Required for backend dev (no rebuild on code change):**
```yaml
backend:
  build:
    context: .
    dockerfile: apps/api/Dockerfile
    target: development          # ← MUST be development target, not production
  volumes:
    - ./apps/api:/app/apps/api   # ← live mount: host code → container
  command: >
    uv run uvicorn api.main:app
    --host 0.0.0.0 --port 8000
    --reload --reload-dir /app/apps/api
```

**Required for frontend dev (Next.js HMR):**
```yaml
frontend:
  build:
    context: .
    dockerfile: apps/web/Dockerfile
    target: development          # ← MUST be development target
  volumes:
    - ./apps/web/src:/app/apps/web/src     # ← live mount for source
    - ./apps/web/public:/app/apps/web/public
    # Do NOT mount node_modules — it must stay in container
```

**Action**: If either service is missing these volume mounts or using the wrong `target`, add/fix them. This is the mechanism that eliminates the need to rebuild on every code change.

**Also verify the worker service** (if present) has a matching live mount:
```yaml
worker:
  volumes:
    - ./apps/api:/app/apps/api
```

### 1.2 — Verify Dockerfile `development` targets support hot-reload

In `apps/api/Dockerfile`, the `development` stage must use `uvicorn --reload`:
```dockerfile
FROM app AS development
CMD ["uv", "run", "uvicorn", "api.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--reload", "--reload-dir", "/app/apps/api"]
```

In `apps/web/Dockerfile`, the `development` stage must use `npm run dev` (Next.js dev server with HMR):
```dockerfile
FROM base AS development
CMD ["npm", "run", "dev"]
```

Both should already be present — verify they are correct and not overridden.

### 1.3 — First boot

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml \
  --env-file .env up --build -d
```

Or using the project script:
```bash
bash scripts/dev.sh
```

Watch startup logs for the first 3 minutes:
```bash
docker compose -f infra/docker-compose.yml logs -f --tail=50
```

**Expected startup sequence:**
1. `postgres` → healthy
2. `redis` → healthy
3. `qdrant` → healthy
4. `migration` job → runs Alembic migrations → exits 0
5. `backend` → "Application startup complete" on port 8000
6. `worker` → "Worker ready, listening on forensic:jobs"
7. `frontend` → "Ready on http://localhost:3000" (Next.js)
8. `caddy` → serving on http://localhost (port 80)

**Fix any service that fails to reach healthy/ready state before proceeding.**

---

## PHASE 2 — STATIC CODE AUDIT (PRE-RUN)

Before any user-facing test, do a complete static pass. Fix every issue found.

### 2.1 — Python: import and syntax validation

```bash
docker compose -f infra/docker-compose.yml exec backend \
  uv run python -c "
import importlib, pkgutil, sys
errors = []
for finder, name, ispkg in pkgutil.walk_packages(['.']):
    try:
        importlib.import_module(name)
    except Exception as e:
        errors.append(f'{name}: {e}')
for e in errors: print(e)
print(f'{len(errors)} import errors')
" 2>&1
```

Also run:
```bash
docker compose -f infra/docker-compose.yml exec backend \
  uv run python -m py_compile $(find apps/api -name "*.py" | tr '\n' ' ') && echo "All Python files compile OK"
```

**Fix every import error and syntax error before proceeding.**

### 2.2 — TypeScript: type-check the frontend

```bash
docker compose -f infra/docker-compose.yml exec frontend \
  npx tsc --noEmit 2>&1
```

**Fix every TypeScript error. Zero tolerance.**

### 2.3 — Stale / duplicate / clutter file audit

```bash
# Find Python __pycache__ that should not be committed
find . -name "__pycache__" -not -path "./.git/*"

# Find .pyc files
find . -name "*.pyc" -not -path "./.git/*"

# Find duplicate agent files (should be exactly one of each agent1–5)
find apps/api/agents -name "agent*.py" | sort

# Find any TODO/FIXME/HACK/STUB markers that indicate incomplete code
grep -rn "TODO\|FIXME\|HACK\|STUB\|NotImplemented\|raise NotImplementedError" \
  apps/api --include="*.py" | grep -v test | grep -v ".pyc"

# Find any placeholder / mock responses leaking into production paths
grep -rn "mock\|placeholder\|fake\|dummy\|lorem\|todo" \
  apps/api --include="*.py" -i | grep -v test | grep -v "#"

# Find stale migration files with conflicts
ls -la apps/api/alembic/versions/

# Find orphaned files not imported anywhere
```

**Action**: Remove all `__pycache__`, `.pyc`, `.DS_Store`, `*.egg-info`, `node_modules` references from git. Ensure `.gitignore` covers them. Remove any genuinely stale/orphaned source files identified by the audit — but read each file before deleting to confirm it is truly dead code.

### 2.4 — Config consistency check

```bash
# Verify every env var used in code exists in .env.example
grep -rn "os.getenv\|Settings\." apps/api --include="*.py" | \
  grep -oP '["'"'"'][A-Z_]+["'"'"']' | sort -u > /tmp/code_env_vars.txt

grep -v "^#" .env.example | grep "=" | cut -d= -f1 | sort > /tmp/example_env_vars.txt

comm -23 /tmp/code_env_vars.txt /tmp/example_env_vars.txt
# Any output here = env var used in code but missing from .env.example → ADD IT
```

Also run the project's own validator:
```bash
bash scripts/validate_env_template_consistency.sh
bash infra/validate_repo_health.sh
```

**Fix every discrepancy.**

### 2.5 — Tool registry integrity check

Every tool name used in agent files must match a constant in `apps/api/core/tool_names.py` AND must be registered in the tool registry.

```bash
docker compose -f infra/docker-compose.yml exec backend \
  uv run python -c "
from core.tool_registry import ToolRegistry
from core.config import get_settings
import asyncio

async def check():
    s = get_settings()
    registry = ToolRegistry(s)
    tools = registry.list_tools()
    print(f'Registered tools ({len(tools)}):')
    for t in sorted(tools):
        print(f'  {t}')

asyncio.run(check())
"
```

Cross-reference with `tool_names.py` constants. Every `TOOL_*` constant must appear in the registry output. Any mismatch = a tool that will silently fail at runtime. Fix by either registering missing tools or removing orphaned constants.

### 2.6 — Database migration integrity

```bash
docker compose -f infra/docker-compose.yml exec backend \
  uv run alembic -c apps/api/alembic.ini history --verbose

docker compose -f infra/docker-compose.yml exec backend \
  uv run alembic -c apps/api/alembic.ini current

docker compose -f infra/docker-compose.yml exec backend \
  uv run alembic -c apps/api/alembic.ini check
# "All migration files present" = OK
```

**Fix any migration conflicts or missing heads before proceeding.**

---

## PHASE 3 — BACKEND API SMOKE TEST

### 3.1 — Health endpoints

```bash
# Direct backend (dev port)
curl -s http://localhost:8000/health | python3 -m json.tool
curl -s http://localhost:8000/readiness | python3 -m json.tool

# Through Caddy reverse proxy
curl -s http://localhost/api/health | python3 -m json.tool
```

**Expected**: `{"status": "ok"}` or similar. Any 5xx = fix before proceeding.

### 3.2 — Auth flow

```bash
# Register (or use dev seed account)
curl -s -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"testuser@forensic.local","password":"TestPass123!","name":"Test Investigator"}' \
  | python3 -m json.tool

# Login — capture the token
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"testuser@forensic.local","password":"TestPass123!"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token',''))")

echo "Token: $TOKEN"
# Must be a non-empty JWT string — if empty, auth is broken. Fix it.

# Verify token works
curl -s http://localhost:8000/api/auth/me \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -m json.tool
```

Also verify the dev seed account works (check `apps/api/core/dev_seed.py` for credentials):
```bash
curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@forensic.local","password":"admin"}' \
  | python3 -m json.tool
```

### 3.3 — Sessions API

```bash
# Create a new session (case)
SESSION=$(curl -s -X POST http://localhost:8000/api/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"E2E Test Case — Real World Photo","description":"Automated end-to-end validation"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id','ERROR'))")

echo "Session ID: $SESSION"
# Must be a UUID — if ERROR, sessions endpoint is broken. Fix it.
```

---

## PHASE 4 — IMAGE UPLOAD & INVESTIGATION (THE CORE TEST)

This is the primary user flow. You will run it with **two image types**:
- **Type A**: Real-world photograph (camera photo, possibly manipulated)
- **Type B**: Digitally-created image (AI-generated, screenshot, graphic)

### 4.1 — Prepare test images

Create or source these test images:

**Image A — Real-world photo** (`test_real_world.jpg`):
- A JPEG photograph taken with a camera (any everyday photo)
- Should ideally have full EXIF data (GPS, camera model, timestamps)
- Minimum 1MP resolution
- If you don't have one available, download a public-domain photo:
  ```bash
  curl -L "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a7/Camponotus_flavomarginatus_ant.jpg/1280px-Camponotus_flavomarginatus_ant.jpg" \
    -o /tmp/test_real_world.jpg
  ```
  Or use one of the sample images already in `storage/evidence/` (two `.jpg` files are present in the project).

**Image B — Digitally-created image** (`test_digital.png`):
- A PNG screenshot, AI-generated image, or digital graphic
- Should NOT have camera EXIF data
- Can be a screenshot of any web page or a generated image
  ```bash
  # Generate a simple test PNG if no other source available:
  python3 -c "
  from PIL import Image, ImageDraw
  img = Image.new('RGB', (800, 600), color=(30, 30, 80))
  draw = ImageDraw.Draw(img)
  draw.rectangle([50, 50, 750, 550], outline=(100, 200, 255), width=3)
  draw.text((200, 250), 'FORENSIC COUNCIL TEST IMAGE', fill=(255, 255, 255))
  img.save('/tmp/test_digital.png')
  print('PNG created')
  "
  ```

### 4.2 — Upload Image A (Real-world JPEG) and run full analysis

```bash
# Upload evidence file
UPLOAD_RESPONSE=$(curl -s -X POST http://localhost:8000/api/cases/${SESSION}/evidence \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/test_real_world.jpg" \
  -F "filename=test_real_world.jpg")

echo "$UPLOAD_RESPONSE" | python3 -m json.tool

EVIDENCE_ID=$(echo "$UPLOAD_RESPONSE" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('evidence_id', d.get('id','ERROR')))")

echo "Evidence ID: $EVIDENCE_ID"
```

```bash
# Trigger investigation (initial analysis — Phase 1)
INVESTIGATION_RESPONSE=$(curl -s -X POST \
  http://localhost:8000/api/investigation/start \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"${SESSION}\",
    \"evidence_id\": \"${EVIDENCE_ID}\",
    \"analysis_depth\": \"initial\"
  }")

echo "$INVESTIGATION_RESPONSE" | python3 -m json.tool

INVESTIGATION_ID=$(echo "$INVESTIGATION_RESPONSE" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('investigation_id', d.get('id','ERROR')))")

echo "Investigation ID: $INVESTIGATION_ID"
```

```bash
# Poll for completion (poll every 5s, max 10 minutes)
for i in $(seq 1 120); do
  STATUS=$(curl -s http://localhost:8000/api/investigation/${INVESTIGATION_ID}/status \
    -H "Authorization: Bearer $TOKEN")
  STATE=$(echo "$STATUS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','unknown'))")
  echo "[${i}] State: $STATE"
  if [[ "$STATE" == "complete" || "$STATE" == "completed" || "$STATE" == "done" ]]; then
    echo "✅ Initial analysis complete"
    break
  fi
  if [[ "$STATE" == "failed" || "$STATE" == "error" ]]; then
    echo "❌ Investigation FAILED"
    echo "$STATUS" | python3 -m json.tool
    # Fetch backend logs for the error
    docker compose -f infra/docker-compose.yml logs backend --tail=100
    docker compose -f infra/docker-compose.yml logs worker --tail=100
    exit 1
  fi
  sleep 5
done
```

**Fetch and validate initial findings:**
```bash
FINDINGS=$(curl -s http://localhost:8000/api/investigation/${INVESTIGATION_ID}/findings \
  -H "Authorization: Bearer $TOKEN")

echo "$FINDINGS" | python3 -m json.tool

# Validate: each of the 5 agents must have fired and produced findings
echo "$FINDINGS" | python3 -c "
import sys, json
d = json.load(sys.stdin)
findings = d.get('findings', d.get('agent_findings', []))
agents_fired = set()
for f in findings:
    agent = f.get('agent_id') or f.get('agent') or f.get('agent_name')
    if agent:
        agents_fired.add(agent)
print(f'Agents fired: {sorted(agents_fired)}')

# For image input: Agent1, Agent3, Agent5 MUST fire. Agent2 and Agent4 may be skipped.
required_for_image = {'Agent1_ImageIntegrity', 'Agent3_ObjectDetection', 'Agent5_Metadata'}
missing = required_for_image - agents_fired
if missing:
    print(f'❌ MISSING REQUIRED AGENTS: {missing}')
    sys.exit(1)
else:
    print('✅ All required agents fired for image input')
"
```

### 4.3 — Run Deep Analysis (Phase 2)

```bash
DEEP_RESPONSE=$(curl -s -X POST \
  http://localhost:8000/api/investigation/${INVESTIGATION_ID}/deepen \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"depth": "deep"}')

echo "$DEEP_RESPONSE" | python3 -m json.tool

# Poll deep analysis (may take longer — ML models)
for i in $(seq 1 180); do
  STATUS=$(curl -s http://localhost:8000/api/investigation/${INVESTIGATION_ID}/status \
    -H "Authorization: Bearer $TOKEN")
  STATE=$(echo "$STATUS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','unknown'))")
  PHASE=$(echo "$STATUS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('phase','?'))")
  echo "[${i}] State: $STATE | Phase: $PHASE"
  if [[ "$STATE" == "complete" || "$STATE" == "completed" ]]; then
    echo "✅ Deep analysis complete"
    break
  fi
  if [[ "$STATE" == "failed" || "$STATE" == "error" ]]; then
    echo "❌ Deep analysis FAILED"
    docker compose -f infra/docker-compose.yml logs backend --tail=150
    docker compose -f infra/docker-compose.yml logs worker --tail=150
    exit 1
  fi
  sleep 5
done
```

### 4.4 — Fetch full report and validate

```bash
REPORT=$(curl -s http://localhost:8000/api/investigation/${INVESTIGATION_ID}/report \
  -H "Authorization: Bearer $TOKEN")

echo "$REPORT" | python3 -m json.tool

# Validate report structure
echo "$REPORT" | python3 -c "
import sys, json
d = json.load(sys.stdin)

errors = []

# Signature — must be present and non-empty for court-admissible report
sig = d.get('signature') or d.get('cryptographic_signature') or {}
if not sig:
    errors.append('MISSING: cryptographic_signature')
else:
    print(f'✅ Signature present: {str(sig)[:80]}...')

# Verdict
verdict = d.get('verdict') or d.get('overall_verdict') or ''
if not verdict:
    errors.append('MISSING: verdict field')
else:
    print(f'✅ Verdict: {verdict}')

# Manipulation probability
prob = d.get('manipulation_probability') or d.get('probability')
if prob is None:
    errors.append('MISSING: manipulation_probability')
else:
    print(f'✅ Manipulation probability: {prob}')

# Confidence
conf = d.get('overall_confidence') or d.get('confidence')
if conf is None:
    errors.append('MISSING: overall_confidence')
else:
    print(f'✅ Confidence: {conf}')

# Agent summaries
agent_summaries = d.get('agent_summaries') or d.get('findings') or []
if not agent_summaries:
    errors.append('MISSING: agent_summaries / findings')
else:
    print(f'✅ Agent summaries: {len(agent_summaries)} entries')

# Narrative
narrative = d.get('narrative') or d.get('executive_summary') or ''
if not narrative or len(narrative) < 50:
    errors.append('MISSING or too short: narrative / executive_summary')
else:
    print(f'✅ Narrative present ({len(narrative)} chars)')

# Chain of custody
custody = d.get('chain_of_custody') or d.get('custody_log') or []
if not custody:
    errors.append('MISSING: chain_of_custody')
else:
    print(f'✅ Chain of custody: {len(custody)} entries')

if errors:
    print()
    for e in errors: print(f'❌ {e}')
    sys.exit(1)
else:
    print()
    print('✅ Report is fully intact and court-admissible structure verified')
"
```

### 4.5 — Export PDF report and validate

```bash
curl -s -X GET \
  "http://localhost:8000/api/investigation/${INVESTIGATION_ID}/report/export?format=pdf" \
  -H "Authorization: Bearer $TOKEN" \
  -o /tmp/forensic_report.pdf

# Verify it's a real PDF (not an error JSON)
file /tmp/forensic_report.pdf
pdfinfo /tmp/forensic_report.pdf 2>/dev/null || python3 -c "
with open('/tmp/forensic_report.pdf','rb') as f:
    header = f.read(8)
    if header.startswith(b'%PDF'):
        print('✅ Valid PDF exported')
    else:
        print(f'❌ Invalid PDF — got: {header}')
        exit(1)
"
```

### 4.6 — Export DOCX report and validate

```bash
curl -s -X GET \
  "http://localhost:8000/api/investigation/${INVESTIGATION_ID}/report/export?format=docx" \
  -H "Authorization: Bearer $TOKEN" \
  -o /tmp/forensic_report.docx

python3 -c "
from docx import Document
try:
    doc = Document('/tmp/forensic_report.docx')
    paras = [p.text for p in doc.paragraphs if p.text.strip()]
    print(f'✅ Valid DOCX — {len(paras)} non-empty paragraphs')
    print('First paragraph:', paras[0] if paras else 'EMPTY')
except Exception as e:
    print(f'❌ DOCX invalid: {e}')
    exit(1)
"
```

### 4.7 — Repeat the entire 4.2–4.6 sequence with Image B (Digital PNG)

Create a new session for the digital image test:

```bash
SESSION_B=$(curl -s -X POST http://localhost:8000/api/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"E2E Test Case — Digital Image","description":"AI-generated or screenshot image test"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id','ERROR'))")

echo "Session B: $SESSION_B"
```

Repeat the upload, initial analysis, deep analysis, report fetch, PDF export, and DOCX export steps with `/tmp/test_digital.png`. The routing logic in `apps/api/core/image_routing.py` and `apps/api/core/media_kind.py` must correctly classify it as a digital/screen-capture image and adapt tool selection accordingly (e.g. Noiseprint++ instead of ViT-ELA for lossless, different Phase 1 tool set).

---

## PHASE 5 — INDIVIDUAL TOOL VERIFICATION

For each tool, verify it fires and produces structured findings (not empty/null output).

### 5.1 — Agent 1: Pixel Integrity tools

These must all fire (based on image type routing):

| Tool constant | Tool name | Expected for |
|---|---|---|
| `TOOL_NEURAL_FINGERPRINT` | `neural_fingerprint` | All images |
| `TOOL_NEURAL_ELA` | `neural_ela` | JPEG (lossy) images |
| `TOOL_NOISE_FINGERPRINT` | `noise_fingerprint` | PNG/lossless images |
| `TOOL_VISUAL_PROFILE` | `visual_evidence_profile` | All images (Gemini or local fallback) |

For each tool result in the findings, verify:
```python
# Each tool result must have:
assert tool_result.get('tool_name') is not None
assert tool_result.get('status') in ('success', 'completed', 'ok')  # NOT 'failed' or 'skipped_error'
assert tool_result.get('findings') or tool_result.get('result')  # non-empty findings
assert tool_result.get('confidence') is not None  # 0.0–1.0
```

**Common bugs to check and fix in Agent 1:**
- `neural_ela` returning `None` for confidence when no JPEG artifacts found → must return `0.0`, not `None`
- `noise_fingerprint` crashing on images smaller than patch size → add size guard
- `visual_evidence_profile` silently skipping when `GEMINI_API_KEY_POLICY_OK=false` without logging a clear reason → ensure fallback to local analysis is logged and produces findings
- Tool name key mismatch between `tool_names.py` constant and registry key → verify exact string match

### 5.2 — Agent 3: Object Detection tools

| Tool | Expected behavior |
|---|---|
| YOLO/DETR object detection | Identifies objects in the scene with bounding boxes |
| Scene classification | Labels the scene type (indoor, outdoor, urban, etc.) |

Verify YOLO/DETR model loads from cache:
```bash
docker compose -f infra/docker-compose.yml exec backend \
  python3 -c "
import os
yolo_dir = os.environ.get('YOLO_MODEL_DIR', '/app/cache/ultralytics')
print('YOLO cache:', os.listdir(yolo_dir) if os.path.exists(yolo_dir) else 'MISSING')
"
```

### 5.3 — Agent 5: Metadata tools

| Tool constant | Expected |
|---|---|
| `TOOL_C2PA_VALIDATOR` | C2PA/CAI provenance chain check |
| `TOOL_METADATA_ANOMALY` | EXIF anomaly score |
| `TOOL_HEX_SIGNATURE` | File magic bytes / format validation |
| `TOOL_EXIF_ISOLATION` | Isolation forest anomaly on EXIF fields |

For real-world JPEG: all 4 should fire. For digital PNG with no EXIF: metadata tools must handle gracefully (not crash) and produce a finding that notes the absence of camera metadata.

### 5.4 — Council Arbiter

After all agents complete:
```bash
# Verify the arbiter ran and produced a signed verdict
echo "$REPORT" | python3 -c "
import sys, json
d = json.load(sys.stdin)

# Challenge loop evidence
challenges = d.get('challenge_log') or d.get('challenges') or []
print(f'Challenge iterations: {len(challenges)}')

# Tribunal escalation (if confidence was low)
tribunal = d.get('tribunal_case') or {}
if tribunal:
    print(f'Tribunal escalated: {tribunal}')

# Severity tier
severity = d.get('severity_tier') or d.get('severity') or ''
print(f'Severity tier: {severity}')

# Cross-modal fusion score
fusion = d.get('cross_modal_fusion_score') or d.get('fusion_score')
print(f'Cross-modal fusion: {fusion}')

# ECDSA signature validation
sig = d.get('signature') or {}
key_id = sig.get('key_id') or sig.get('signing_key_id')
sig_value = sig.get('signature') or sig.get('value')
print(f'Signing key ID: {key_id}')
print(f'Signature value (first 40 chars): {str(sig_value)[:40]}...' if sig_value else 'MISSING')
"
```

---

## PHASE 6 — FRONTEND END-TO-END USER JOURNEY

Open a real browser (or use Playwright if available) and walk through the complete user journey.

### 6.1 — Landing page

Navigate to `http://localhost` (Caddy) or `http://localhost:3000` (direct).

Verify:
- [ ] Page loads without console errors (`F12 → Console`)
- [ ] No React hydration errors
- [ ] Auth state is correctly shown (logged-out state)
- [ ] "Login" / "Get Started" CTAs visible

### 6.2 — Login flow

1. Click Login
2. Enter credentials (dev seed: `admin@forensic.local` / `admin` or the account you registered)
3. Verify redirect to dashboard / case list
4. Verify JWT stored correctly (check browser localStorage or cookies — not plaintext password)

### 6.3 — Create a case and upload evidence

1. Click "New Case" / "New Investigation"
2. Fill in case name and description
3. Upload `/tmp/test_real_world.jpg` via the upload modal
4. Verify upload progress indicator appears and completes
5. Verify file is accepted (not rejected by `fileValidation.ts`)
6. Verify upload success modal / confirmation

**Common frontend bugs to check:**
- Upload modal not closing after success
- File validation rejecting valid MIME types (check `apps/web/src/lib/fileValidation.ts`)
- `NEXT_PUBLIC_API_URL` pointing to wrong port through Caddy vs direct backend

### 6.4 — Watch agent progress in real-time

After upload, the investigation should auto-start. Verify:
- [ ] `AgentProgressDisplay` component shows all 5 agents
- [ ] Each agent card shows: `pending → running → complete` state transitions
- [ ] Agent tool steps are visible (the sub-tool progress for each agent)
- [ ] No agent card is stuck in `running` state indefinitely
- [ ] WebSocket or SSE connection is established (check Network tab for `/api/investigation/*/stream` or similar)
- [ ] Live updates arrive without polling (no repeated XHR every 2 seconds — must be SSE/WS push)

Check SSE connection:
```bash
# Verify SSE endpoint works
curl -s -N -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/investigation/${INVESTIGATION_ID}/stream" &
sleep 10 && kill %1
# Should see JSON event lines streaming — not silence or 404
```

### 6.5 — Results page

After analysis completes:
- [ ] `DynamicResultClient` renders the verdict panel
- [ ] Verdict badge (green/yellow/red) is correct and visible
- [ ] Manipulation probability gauge/bar shows a value
- [ ] All agent finding cards are visible with their individual verdicts
- [ ] Each agent card shows tool-level findings (expandable or visible)
- [ ] Narrative / executive summary text is present and substantive (not placeholder text)
- [ ] Confidence score is shown
- [ ] Chain of custody section is present

### 6.6 — Report export from UI

1. Click "Export PDF" — verify download starts and file is a valid PDF
2. Click "Export DOCX" — verify download starts and file is a valid DOCX
3. Verify the exported file name includes case ID or timestamp (not generic "report.pdf")

### 6.7 — Deep analysis trigger from UI

If the UI has a "Run Deep Analysis" button:
1. Click it
2. Verify the agent progress display reactivates
3. Wait for completion
4. Verify the result page updates with Phase 2 findings
5. Verify deep-pass tool findings appear (TruFor, BusterNet, F3-Net, ManTra-Net for images)

---

## PHASE 7 — ERROR HANDLING & RESILIENCE

### 7.1 — Upload an unsupported file type

Upload a `.txt` or `.exe` file. Verify:
- Frontend rejects it at upload with a clear error message (not a crash)
- If it reaches the backend, backend returns 422 with a clear message
- No unhandled exception in backend logs

### 7.2 — Upload a corrupt image

```bash
# Create a corrupt JPEG (valid header, garbage body)
python3 -c "
with open('/tmp/corrupt.jpg', 'wb') as f:
    f.write(b'\xff\xd8\xff\xe0' + b'\x00' * 1000 + b'CORRUPT DATA HERE')
"
```

Upload it and verify:
- Backend handles it gracefully
- Investigation completes (or fails cleanly with a readable error status)
- No 500 crash, no unhandled exception
- Error is surfaced in the UI, not a blank screen

### 7.3 — API auth errors

```bash
# Try accessing protected endpoint without token
curl -s http://localhost:8000/api/sessions | python3 -m json.tool
# Expected: 401 Unauthorized

# Try with expired/invalid token
curl -s http://localhost:8000/api/sessions \
  -H "Authorization: Bearer invalidtoken123" | python3 -m json.tool
# Expected: 401 Unauthorized
```

---

## PHASE 8 — PERFORMANCE & RESOURCE CHECK

### 8.1 — Container resource usage

```bash
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"
```

**Expected bounds in dev (no concurrent load):**
- `backend`: < 500MB RAM idle
- `worker`: < 1GB RAM idle (ML model workers loaded)
- `frontend`: < 256MB RAM
- `postgres`: < 256MB RAM
- `redis`: < 128MB RAM
- `qdrant`: < 512MB RAM

If any container is OOM-killed or approaching memory limits, check:
- `FORENSIC_MAX_WORKERS` env var (should be 2 in Docker dev)
- ML model loading strategy (lazy load vs eager load)

### 8.2 — Log noise check

```bash
docker compose -f infra/docker-compose.yml logs backend 2>&1 | grep -iE "error|exception|traceback|critical" | grep -v "404\|INFO\|DEBUG"
docker compose -f infra/docker-compose.yml logs worker 2>&1 | grep -iE "error|exception|traceback|critical"
```

**Action**: Any `ERROR` or `CRITICAL` log line that is not an intentional user error (like 401 from a bad token test) must be investigated and fixed.

---

## PHASE 9 — COMPLETE ITERATION 2 AND 3

After fixing all issues found in Phases 0–8, run a second full iteration:

**Iteration 2:**
1. Restart Docker stack fresh (do NOT `down -v` — preserve model cache):
   ```bash
   docker compose -f infra/docker-compose.yml restart
   ```
2. Run the full image upload → initial analysis → deep analysis → report → export flow for **both** image types
3. Verify zero errors in backend logs during the entire flow
4. Verify every tool fires and every finding is non-empty

**Iteration 3 (final production gate):**
1. Run `bash infra/validate_production_readiness.sh`
2. Run `bash infra/validate_repo_health.sh`
3. Run all backend tests:
   ```bash
   docker compose -f infra/docker-compose.yml exec backend \
     uv run pytest apps/api/tests/ -v --tb=short 2>&1
   ```
4. Run all frontend tests:
   ```bash
   docker compose -f infra/docker-compose.yml exec frontend \
     npm test -- --passWithNoTests 2>&1
   ```
5. **Fix every test failure.** Do not mark tests as skipped — fix the underlying code.

---

## PHASE 10 — CLEANUP & FINAL STATE

### 10.1 — Stale file removal

```bash
# Remove all __pycache__ and .pyc (these should never be committed)
find . -type d -name __pycache__ -not -path "./.git/*" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -not -path "./.git/*" -delete 2>/dev/null || true

# Remove any temp/scratch files created during development
find . -name "*.tmp" -o -name "*.bak" -o -name "*.orig" | grep -v ".git" | xargs rm -f 2>/dev/null || true

# Remove any leftover test output files
rm -f /tmp/forensic_report.pdf /tmp/forensic_report.docx
rm -f /tmp/test_real_world.jpg /tmp/test_digital.png /tmp/corrupt.jpg
```

### 10.2 — Verify `.gitignore` covers all generated files

```
# These must be in .gitignore:
__pycache__/
*.pyc
*.pyo
.env
*.env.local
node_modules/
.next/
dist/
build/
*.egg-info/
.pytest_cache/
.mypy_cache/
storage/evidence/*
!storage/evidence/.gitkeep
cache/
*.log
```

### 10.3 — Final checklist

Run this checklist and confirm every item passes:

```
[ ] docker compose up --build succeeds with zero errors
[ ] All 7 services reach healthy state
[ ] Backend /health returns 200
[ ] Frontend loads at http://localhost:3000 with zero console errors
[ ] Auth registration and login work
[ ] Session creation works
[ ] Real-world JPEG upload → initial analysis → deep analysis → report → PDF export = 100% clean
[ ] Digital PNG upload → initial analysis → deep analysis → report → PDF export = 100% clean
[ ] Agent 1 (Pixel Integrity) fires all appropriate tools for each image type
[ ] Agent 3 (Object Detection) fires and produces scene/object findings
[ ] Agent 5 (Metadata) fires and produces EXIF/metadata findings
[ ] Council Arbiter produces a cryptographically signed verdict
[ ] Report narrative is substantive (not placeholder text)
[ ] Chain of custody is logged and present in report
[ ] PDF export is a valid PDF with report content
[ ] DOCX export is a valid DOCX with report content
[ ] Frontend result page shows green verdict badge for non-manipulated test images
[ ] Live code mount works — editing a Python file takes effect without rebuild
[ ] All Python tests pass (or are documented with reason for pending status)
[ ] All TypeScript/frontend tests pass
[ ] Zero ERROR lines in docker logs for a clean end-to-end run
[ ] No stale/duplicate/orphaned files in repo
[ ] .env.example has all required variables documented
[ ] README.md reflects actual startup command
```

---

## KNOWN CRITICAL BUG CLASSES TO WATCH FOR

Based on the codebase structure, these are the most likely failure points. Check each explicitly:

### B1 — `GEMINI_API_KEY_POLICY_OK` missing from `.env`
**Symptom**: `ValidationError: GEMINI_API_KEY_POLICY_OK must be explicitly set`
**Fix**: Add `GEMINI_API_KEY_POLICY_OK=true` (or `false`) to `.env`

### B2 — Tool registry key mismatch
**Symptom**: Tool fires but result has `status: "not_found"` or tool is silently skipped
**Fix**: Verify string in `tool_names.py` TOOL_* constant exactly matches the key used to register the handler in `ToolRegistry`

### B3 — Arbiter signing key not initialized
**Symptom**: Report missing `signature` field or `signing` error in logs
**Fix**: Verify `apps/api/core/signing.py` `get_keystore()` initializes on startup; verify migration `0002_add_signing_keys_and_traces.py` ran successfully

### B4 — Worker not picking up jobs
**Symptom**: Investigation stays in `pending` forever
**Fix**: Verify `USE_REDIS_WORKER=true` in backend env; verify `worker` service is running; verify Redis is healthy; check `inter_agent_bus.py` queue name matches

### B5 — Frontend SSE/WebSocket disconnection
**Symptom**: Progress display freezes, never updates
**Fix**: Check `_websocket.py` or `sse.py` route; verify CORS allows SSE from frontend origin; check Caddy proxy config for `Connection: keep-alive` and `X-Accel-Buffering: no` headers for SSE

### B6 — Alembic migration not applied
**Symptom**: `relation "agent_signing_keys" does not exist` on startup
**Fix**: Verify migration service ran; run manually: `docker compose exec backend uv run alembic upgrade head`

### B7 — ML model download blocked in offline mode
**Symptom**: Model not found, falling back, or crashing on first analysis
**Fix**: With `OFFLINE_MODE=true`, models must already be in `HF_HOME` cache. Either set `OFFLINE_MODE=false` for first run to download, or pre-populate the volume. Check if models exist: `docker compose exec backend ls /app/cache/huggingface/hub/`

### B8 — EasyOCR / Tesseract not finding language data
**Symptom**: OCR tool crashes with "language not found"
**Fix**: Verify `tesseract-ocr-eng` installed in Dockerfile base stage; verify `EASYOCR_MODEL_DIR` is writable

### B9 — PDF export empty or malformed
**Symptom**: Downloaded PDF is 0 bytes or fails to open
**Fix**: Check `pdf_report_exporter.py`; verify `reportlab` or `weasyprint` (whichever is used) is installed; verify report data is properly serialized before passing to exporter

### B10 — Frontend `NEXT_PUBLIC_API_URL` wrong in dev
**Symptom**: API calls 404 or CORS error from frontend
**Fix**: In `docker-compose.dev.yml`, `NEXT_PUBLIC_API_URL` must match where the browser can reach the backend (through Caddy at `http://localhost/api` or direct at `http://localhost:8000`)

---

## DELIVERABLE

When this prompt is fully executed, the project must be in a state where:

1. `git clone <repo> && cp .env.example .env && <fill keys> && bash scripts/dev.sh` brings up a fully working forensic platform
2. Uploading any real-world JPEG or digital PNG runs all relevant forensic tools, produces substantive findings, and generates a court-admissible signed report
3. No code changes are needed after the final green state — only API key configuration
4. Live code mounts are in place so development iteration is instant (no rebuilds)
5. The project is ready for the final sanitisation cleanup pass

**Stop only when all three full iterations complete with zero errors and the final checklist is 100% checked.**
