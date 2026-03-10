# Project Structure & Organization Guide

## Complete Project Organization

```
Forensic-Council/
├── backend/                          # Python FastAPI backend
│   ├── api/                         # API routes
│   │   ├── routes/                  # Endpoint definitions
│   │   │   ├── investigation.py     # Investigation endpoints
│   │   │   ├── hitl.py             # Human-in-the-loop routes
│   │   │   ├── auth.py             # Authentication
│   │   │   ├── metrics.py          # Metrics collection
│   │   │   └── sessions.py         # Session management
│   │   ├── main.py                 # API application setup
│   │   └── schemas.py              # API schemas
│   ├── agents/                      # Forensic agents
│   │   ├── base_agent.py           # Base agent class
│   │   ├── agent1_image.py         # Image analysis agent
│   │   ├── agent2_audio.py         # Audio analysis agent
│   │   ├── agent3_object.py        # Object detection agent
│   │   ├── agent4_video.py         # Video analysis agent
│   │   ├── agent5_metadata.py      # Metadata analysis agent
│   │   └── arbiter.py              # Decision arbitrator
│   ├── core/                        # Core modules
│   │   ├── config.py               # Configuration management
│   │   ├── auth.py                 # Authentication logic
│   │   ├── logging.py              # Logging setup
│   │   ├── migrations.py           # Database migrations
│   │   ├── retry.py                # Retry logic
│   │   └── observability.py        # OpenTelemetry setup
│   ├── infra/                       # Infrastructure
│   │   ├── postgres_client.py       # PostgreSQL client
│   │   ├── redis_client.py          # Redis client
│   │   ├── qdrant_client.py         # Vector DB client
│   │   ├── evidence_store.py        # Evidence storage
│   │   └── storage.py               # File storage helpers
│   ├── orchestration/               # Workflow orchestration
│   │   ├── pipeline.py             # Investigation pipeline
│   │   └── session_manager.py      # Session management
│   ├── tools/                       # Agent tools
│   │   ├── image_tools.py          # Image analysis tools
│   │   ├── audio_tools.py          # Audio analysis tools
│   │   └── ... (more tools)
│   ├── tests/                       # Tests
│   ├── pyproject.toml              # Python dependencies
│   └── README.md                    # Backend docs
│
├── frontend/                         # Next.js React frontend
│   ├── src/
│   │   ├── app/                    # Next.js pages
│   │   │   ├── api/               # API routes
│   │   │   ├── evidence/          # Investigation page
│   │   │   ├── result/            # Results page
│   │   │   ├── session-expired/   # Auth timeout page
│   │   │   ├── layout.tsx         # Root layout
│   │   │   ├── page.tsx           # Landing page
│   │   │   └── globals.css        # Global styles
│   │   │
│   │   ├── components/            # React components
│   │   │   ├── evidence/          # Evidence page components
│   │   │   │   ├── HeaderSection.tsx
│   │   │   │   ├── FileUploadSection.tsx
│   │   │   │   ├── AgentProgressDisplay.tsx
│   │   │   │   ├── CompletionBanner.tsx
│   │   │   │   ├── ErrorDisplay.tsx
│   │   │   │   ├── HITLCheckpointModal.tsx
│   │   │   │   └── index.ts
│   │   │   ├── ui/                # UI components
│   │   │   │   ├── dialog.tsx
│   │   │   │   ├── AgentIcon.tsx
│   │   │   │   └── AgentResponseText.tsx
│   │   │   └── DevErrorOverlay.tsx
│   │   │
│   │   ├── hooks/                 # Custom hooks
│   │   │   ├── useForensicData.ts
│   │   │   ├── useSimulation.ts
│   │   │   └── useSound.ts
│   │   │
│   │   ├── lib/                   # Utilities
│   │   │   ├── api.ts            # API client
│   │   │   ├── constants.ts       # Constants
│   │   │   ├── schemas.ts         # Validation
│   │   │   └── utils.ts           # Helpers
│   │   │
│   │   ├── types/                 # TypeScript types
│   │   │   ├── index.ts
│   │   │   └── global.d.ts
│   │   │
│   │   └── __tests__/             # Tests
│   │       ├── hooks/
│   │       ├── lib/
│   │       └── types/
│   │
│   ├── public/                     # Static assets
│   ├── ARCHITECTURE.md             # Component architecture
│   ├── COMPONENTS.md               # Component reference
│   ├── README.md                  # Complete frontend guide
│   ├── package.json               # Dependencies
│   ├── tsconfig.json              # TypeScript config
│   ├── next.config.ts             # Next.js config
│   └── jest.config.ts             # Jest config
│
├── docs/                            # Documentation
│   ├── API.md                      # API documentation
│   ├── ARCHITECTURE.md             # System architecture
│   ├── SECURITY.md                 # Security guide
│   ├── CONTRIBUTING.md             # Contribution guide
│   ├── DECISIONS.md                # Technical decisions
│   ├── SCHEMAS.md                  # Data schemas
│   ├── agent_capabilities.md       # Agent capabilities
│   ├── docker/                     # Docker documentation
│   ├── status/                     # Status reports
│   └── test/                       # Testing guides
│
├── .env.example                     # Environment template
├── .gitignore                       # Git ignore rules
├── LICENSE                          # License
├── README.md                        # Project README
├── CHANGELOG.md                     # Version history
└── manage.ps1                       # PowerShell manager (.\manage.ps1 up / dev / down)
```

## Key Organization Principles

### 1. **Separation of Concerns**

**Backend:**
- `api/` - HTTP endpoints only
- `agents/` - AI agent logic
- `core/` - Infrastructure concerns
- `tools/` - Agent tool implementations
- `orchestration/` - Workflow logic

**Frontend:**
- `app/` - Page routes only
- `components/` - Pure UI components
- `hooks/` - State and side effects
- `lib/` - Utilities and external integrations

### 2. **Feature-Based Organization**

Components are organized by feature rather than type:

```
components/
├── evidence/           # Evidence investigation feature
│   ├── HeaderSection.tsx
│   ├── FileUploadSection.tsx
│   ├── AgentProgressDisplay.tsx
│   └── ... (related components)
└── ui/                # Reusable UI building blocks
    ├── dialog.tsx
    ├── AgentIcon.tsx
    └── ...
```

This makes it easy to:
- Find all evidence-related components
- Move features between projects
- Understand feature dependencies

### 3. **Clear Routing**

**Frontend Pages:**
- `/` - Landing page
- `/evidence` - Investigation page
- `/result` - Results page
- `/session-expired` - Auth timeout

**API Endpoints:**
- `/api/v1/investigate` - Start investigation
- `/api/v1/sessions/{id}` - Get session
- `/api/v1/hitl/decision` - Submit HITL decision
- `/api/v1/auth/login` - Authentication

### 4. **Type Safety**

- All components have TypeScript interfaces
- API responses validated with Pydantic (backend) and Zod (frontend)
- Shared types in dedicated modules

### 5. **Documentation Colocation**

Documentation lives near the code it describes:

- `frontend/ARCHITECTURE.md` - Frontend structure
- `frontend/COMPONENTS.md` - Component reference
- `backend/README.md` - Backend setup
- `docs/API.md` - API documentation

---

## Navigation Guide

### Adding a New Component

1. **Create in proper directory**
   ```
   frontend/src/components/evidence/NewComponent.tsx
   ```

2. **Export from index**
   ```typescript
   // frontend/src/components/evidence/index.ts
   export { NewComponent } from "./NewComponent";
   ```

3. **Use in page**
   ```typescript
   import { NewComponent } from "@/components/evidence";
   ```

### Adding a New Page

1. **Create in app directory**
   ```
   frontend/src/app/newpage/page.tsx
   ```

2. **Implement as React component**
   ```typescript
   export default function NewPage() {
     return <div>Page content</div>;
   }
   ```

3. **Accessible at `/newpage`** via Next.js routing

### Adding a New API Endpoint

1. **Create route file**
   ```
   backend/api/routes/newroute.py
   ```

2. **Define endpoint**
   ```python
   @router.post("/endpoint")
   async def my_endpoint(data: MySchema):
       return {"result": "data"}
   ```

3. **Include in main.py**
   ```python
   app.include_router(newroute.router)
   ```

### Adding a New Agent

1. **Create agent file**
   ```
   backend/agents/agent_name.py
   ```

2. **Inherit from BaseAgent**
   ```python
   from agents.base_agent import BaseAgent
   
   class AgentName(BaseAgent):
       async def run(self):
           ...
   ```

3. **Register in pipeline**
   ```python
   # orchestration/pipeline.py
   agents.append(AgentName(...))
   ```

---

## File Naming Conventions

### Frontend

```
Components:          PascalCase    (HeaderSection.tsx)
Hooks:               camelCase     (useForensicData.ts)
Utilities:           camelCase     (constants.ts)
Pages:               lowercase     (page.tsx)
Tests:               .test.ts      (component.test.ts)
Interfaces:          PascalCase    (ComponentProps)
```

### Backend

```
Modules:             snake_case    (auth.py)
Classes:             PascalCase    (BaseAgent)
Functions:           snake_case    (get_user())
Constants:           UPPER_CASE    (MAX_RETRIES)
Tests:               test_*.py     (test_auth.py)
```

---

## Dependency Management

### Frontend Dependencies

**Core:**
- `next` - React framework
- `react` - UI library
- `react-dom` - DOM bindings

**UI & Animation:**
- `tailwindcss` - Styling
- `framer-motion` - Animations
- `lucide-react` - Icons

**Utilities:**
- `zod` - Data validation
- `clsx` - Class names

**Development:**
- `typescript` - Type checking
- `eslint` - Linting
- `jest` - Testing

### Backend Dependencies

**Core:**
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `pydantic` - Data validation

**Database:**
- `asyncpg` - PostgreSQL driver
- `qdrant-client` - Vector DB
- `redis[asyncio]` - Cache

**ML & Analysis:**
- `langgraph` - Agent framework
- `transformers` - NLP models
- `opencv` - Computer vision
- `librosa` - Audio processing

**Deployment:**
- `python-dotenv` - Environment config
- `cryptography` - Encryption

---

## Build & Deployment

### Development Setup

```bash
# Frontend
cd frontend
npm install
npm run dev

# Backend (in separate terminal)
cd backend
uv sync
uv run uvicorn api.main:app --reload
```

### Production Build

```bash
# Frontend
npm run build
npm start

# Backend
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

### Docker Deployment

```bash
# Build images
docker-compose build

# Start services
docker-compose up

# Production
docker compose -f docs/docker/docker-compose.yml -f docs/docker/docker-compose.prod.yml --env-file .env up
```

---

## Development Workflow

### Before Making Changes

1. Read relevant documentation
2. Understand current architecture
3. Check similar implementations
4. Plan component structure

### While Making Changes

1. Follow naming conventions
2. Write clear code with comments
3. Update related documentation
4. Test thoroughly

### After Making Changes

1. Run linting: `npm run lint`
2. Run tests: `npm test`
3. Update documentation
4. Commit with clear messages

---

## Quick Reference

### Frontend

| Task | Command |
|------|---------|
| Start dev server | `npm run dev` |
| Build | `npm run build` |
| Lint | `npm run lint` |
| Test | `npm test` |
| Type check | `npm run type-check` |

### Backend

| Task | Command |
|------|---------|
| Start dev | `python -m uvicorn api.main:app --reload` |
| Run tests | `pytest` |
| Format code | `ruff format .` |
| Lint | `ruff check .` |

### Docker

| Task | Command |
|------|---------|
| Build all | `docker compose -f docs/docker/docker-compose.yml --env-file .env build` |
| Start all | `docker compose -f docs/docker/docker-compose.yml --env-file .env up` |
| Stop all | `docker compose -f docs/docker/docker-compose.yml --env-file .env down` |
| View logs | `docker compose -f docs/docker/docker-compose.yml --env-file .env logs -f` |

---

## Getting Help

### Documentation
- **Frontend:** `frontend/ARCHITECTURE.md`, `frontend/COMPONENTS.md`
- **Backend:** `backend/README.md`
- **API:** `docs/API.md`
- **Deployment:** `docs/docker/DOCKER_BUILD.md`

### Code Examples
- **Components:** `frontend/src/components/evidence/`
- **Hooks:** `frontend/src/hooks/`
- **Agents:** `backend/agents/`

### Common Issues
- **Setup:** See respective README files
- **Errors:** Check logs and error messages
- **Performance:** Profile with browser/profiling tools

---

## Checklist for New Features

- [ ] Created in appropriate directory
- [ ] Follows naming conventions
- [ ] TypeScript types defined
- [ ] Documentation written
- [ ] Tests added
- [ ] Linting passes
- [ ] Tested manually
- [ ] Performance considered
- [ ] Accessibility checked
- [ ] Related docs updated

---

**Last Updated:** March 8, 2026  
**Version:** 1.0.0  
**Status:** Production Ready
