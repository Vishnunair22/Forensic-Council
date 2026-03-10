# Documentation Index

Welcome to the Forensic Council project! This document provides a guide to all available documentation.

## 🚀 Quick Start

**New to the project?** Start here:
1. Read [README.md](../README.md) - Project overview
2. Read [PROJECT_STRUCTURE.md](./PROJECT_STRUCTURE.md) - How the project is organized
3. Choose your role below

## 📚 Documentation by Role

### Frontend Developer

**Setup & Development:**
- [Frontend README](../frontend/README.md) - Complete setup guide
- [ARCHITECTURE.md](../frontend/ARCHITECTURE.md) - Component structure
- [COMPONENTS.md](../frontend/COMPONENTS.md) - Component reference

**Key Topics:**
- Component development workflow
- Styling with Tailwind CSS
- State management with hooks
- API integration
- Testing frontend code

### Backend Developer

**Setup & Development:**
- [Backend README](../backend/README.md) - Backend setup
- [API Documentation](../docs/API.md) - Endpoint reference
- [Agent Capabilities](../docs/agent_capabilities.md) - Agent features

**Key Topics:**
- Setting up PostgreSQL/Redis/Qdrant
- Creating new agents
- Adding API endpoints
- Database migrations
- Testing backend code

### DevOps/Infrastructure

**Setup & Deployment:**
- [Docker Build Guide](../docs/docker/DOCKER_BUILD.md) - Container setup
- [Security Guide](../docs/SECURITY.md) - Security practices
- [Architecture Guide](../docs/ARCHITECTURE.md) - System design

**Key Topics:**
- Building Docker images
- Docker Compose setup
- Environment configuration
- Production deployment
- Monitoring & logging

### Project Manager

**Understanding the Project:**
- [README.md](../README.md) - Project overview
- [DECISIONS.md](../docs/DECISIONS.md) - Technical decisions
- [CHANGELOG.md](../CHANGELOG.md) - Version history
- [Development Status](../docs/status/Development-Status.md) - Current status

**Key Topics:**
- Feature set
- Technical decisions
- Project timeline
- Known issues
- Roadmap

## 📖 Full Documentation Structure

```
Documentation/
├── README.md                    [Project overview & features]
├── PROJECT_STRUCTURE.md         [Project organization guide] ← START HERE
├── CHANGELOG.md                [Version history]
│
├── frontend/
│   ├── README.md               [Frontend complete guide]
│   ├── ARCHITECTURE.md         [Component architecture]
│   ├── COMPONENTS.md           [Component reference]
│   └── src/...                 [Source code]
│
├── backend/
│   ├── README.md               [Backend setup guide]
│   └── src/...                 [Source code]
│
└── docs/
    ├── API.md                  [API endpoint reference]
    ├── ARCHITECTURE.md         [System architecture]
    ├── SECURITY.md             [Security practices]
    ├── DECISIONS.md            [Technical decisions]
    ├── SCHEMAS.md              [Data schemas]
    ├── CONTRIBUTING.md         [Contribution guide]
    ├── agent_capabilities.md   [Agent features]
    ├── docker/                 [Docker guides]
    ├── status/                 [Status reports]
    └── test/                   [Testing guides]
```

## 🎯 By Task

### "I want to..."

#### Run the project locally
→ [Frontend README Setup](../frontend/README.md#quick-start) + [Backend README Setup](../backend/README.md)

#### Add a new component
→ [ARCHITECTURE.md](../frontend/ARCHITECTURE.md#adding-new-components) + [COMPONENTS.md](../frontend/COMPONENTS.md)

#### Add a new API endpoint
→ [API Documentation](../docs/API.md) + [Backend README](../backend/README.md)

#### Deploy to production
→ [Docker Build Guide](../docs/docker/DOCKER_BUILD.md) + [Security Guide](../docs/SECURITY.md)

#### Understand the system
→ [System Architecture](../docs/ARCHITECTURE.md) + [Technical Decisions](../docs/DECISIONS.md)

#### Fix a bug
→ [Relevant README](../frontend/README.md) + Source code + [Testing Guide](../docs/test/TESTING.md)

#### Add a new feature
→ [PROJECT_STRUCTURE.md](./PROJECT_STRUCTURE.md) + Relevant README + Source code

#### Understand security
→ [Security Guide](../docs/SECURITY.md) + [DECISIONS.md](../docs/DECISIONS.md)

## 🔍 Quick Links by Topic

### Frontend

| Topic | Document |
|-------|----------|
| Getting started | [Frontend README](../frontend/README.md) |
| Component structure | [ARCHITECTURE.md](../frontend/ARCHITECTURE.md) |
| All components | [COMPONENTS.md](../frontend/COMPONENTS.md) |
| Development workflow | [README - Development](../frontend/README.md#development-workflow) |
| Styling | [README - Styling](../frontend/README.md#styling) |
| API integration | [README - API Integration](../frontend/README.md#api-integration) |
| Testing | [README - Testing](../frontend/README.md#testing) |
| Deployment | [README - Deployment](../frontend/README.md#deployment) |

### Backend

| Topic | Document |
|-------|----------|
| Getting started | [Backend README](../backend/README.md) |
| API endpoints | [API.md](../docs/API.md) |
| Agent capabilities | [agent_capabilities.md](../docs/agent_capabilities.md) |
| Database schemas | [SCHEMAS.md](../docs/SCHEMAS.md) |
| Security | [SECURITY.md](../docs/SECURITY.md) |

### DevOps

| Topic | Document |
|-------|----------|
| Docker setup | [DOCKER_BUILD.md](../docs/docker/DOCKER_BUILD.md) |
| Docker Compose | [docker-compose.yml](../docs/docker/docker-compose.yml) |
| Environment config | [Backend README - Config](../backend/README.md) |
| Deployment | [DOCKER_BUILD.md - Deployment](../docs/docker/DOCKER_BUILD.md) |

### General

| Topic | Document |
|-------|----------|
| Project overview | [README.md](../README.md) |
| Project structure | [PROJECT_STRUCTURE.md](./PROJECT_STRUCTURE.md) |
| System architecture | [ARCHITECTURE.md](../docs/ARCHITECTURE.md) |
| Technical decisions | [DECISIONS.md](../docs/DECISIONS.md) |
| Version history | [CHANGELOG.md](../CHANGELOG.md) |

## 🛠️ Development Setup

### Prerequisites
- Node.js 18+ (Frontend)
- Python 3.11+ (Backend)
- Docker & Docker Compose (Optional but recommended)
- PostgreSQL, Redis, Qdrant (Development)

### Quick Setup

**Frontend:**
```bash
cd frontend
npm install
npm run dev        # Runs on http://localhost:3000
```

**Backend:**
```bash
cd backend
uv sync
uv run uvicorn api.main:app --reload  # Runs on http://localhost:8000
```

**With Docker:**
```bash
.\manage.ps1 up  # All services with Docker
```

For detailed setup, see:
- [Frontend README - Quick Start](../frontend/README.md#quick-start)
- [Backend README - Installation](../backend/README.md#installation)
- [Docker Build Guide](../docs/docker/DOCKER_BUILD.md)

## 📋 Common Commands

### Frontend
```bash
npm run dev              # Start development server
npm run build           # Build for production
npm run lint            # Check code style
npm test                # Run tests
npm run type-check      # TypeScript check
```

### Backend
```bash
uv run uvicorn api.main:app --reload   # Dev server
uv run pytest                          # Run tests
ruff check .                           # Lint
ruff format .                          # Format code
```

### Docker
```bash
.\manage.ps1 up     # Build and start all services
.\manage.ps1 dev    # Start with hot-reload
.\manage.ps1 down   # Stop all services
.\manage.ps1 logs   # View logs
```

## ✅ Quality Checklist

Before committing code:
- [ ] Code follows naming conventions
- [ ] TypeScript/Python syntax valid
- [ ] Linting passes
- [ ] Tests pass
- [ ] Documentation updated
- [ ] No console errors/warnings
- [ ] Performance acceptable
- [ ] Accessibility considered

## 🐛 Troubleshooting

### Common Issues

**Frontend not loading:**
1. Check `npm run dev` is running
2. Verify API is running on `:8000`
3. Check `.env.local` configuration
4. Clear `.next` cache: `rm -rf .next`

**API not responding:**
1. Check backend is running: `http://localhost:8000/health`
2. Verify database connections
3. Check logs for errors
4. Verify environment variables

**Build failures:**
1. Clear node_modules: `rm -rf node_modules && npm install`
2. Check Node version: `node -v` (should be 18+)
3. Review error messages
4. Check documentation

**Docker issues:**
1. Ensure Docker daemon is running
2. Check port availability
3. Review docker-compose.yml
4. Check logs: `docker-compose logs`

## 📞 Getting Help

### Documentation
1. Check relevant README files
2. Search documentation
3. Review code comments
4. Check GitHub issues

### Development
1. Review similar code
2. Check test files for examples
3. Ask in team channels
4. Create GitHub issue if stuck

### Production
1. Check deployment guide
2. Review security guide
3. Check monitoring/logging
4. Contact DevOps team

## 🔄 Keeping Documentation Updated

When you make changes:
1. Update relevant documentation
2. Add comments to complex code
3. Update CHANGELOG.md
4. Review this index for relevance

## 📚 Additional Resources

### External Documentation
- [Next.js Docs](https://nextjs.org/docs)
- [React Docs](https://react.dev)
- [FastAPI Docs](https://fastapi.tiangolo.com)
- [Tailwind CSS](https://tailwindcss.com)
- [Framer Motion](https://www.framer.com/motion)
- [PostgreSQL Docs](https://www.postgresql.org/docs)

### Tools & Libraries
- [ESLint](https://eslint.org) - Code linting
- [Prettier](https://prettier.io) - Code formatting
- [Jest](https://jestjs.io) - Testing framework
- [Pytest](https://pytest.org) - Python testing
- [Docker](https://docker.com) - Containerization

## 📝 Document Versions

| Document | Last Updated | Version |
|----------|--------------|---------|
| README.md | March 10, 2026 | 1.0.0 |
| ARCHITECTURE.md | March 8, 2026 | 1.0.0 |
| COMPONENTS.md | March 8, 2026 | 1.0.0 |
| API.md | March 8, 2026 | 1.0.0 |
| SECURITY.md | March 8, 2026 | 1.0.0 |
| PROJECT_STRUCTURE.md | March 8, 2026 | 1.0.0 |
| TESTING.md | March 10, 2026 | 1.0.1 |
| Development-Status.md | March 10, 2026 | 1.0.1 |

## 🎉 You're All Set!

Start with [PROJECT_STRUCTURE.md](./PROJECT_STRUCTURE.md) for the full overview, then dive into the role-specific documentation above.

Happy coding! 🚀

---

**Questions?** Check the relevant README or create an issue.

**Found a problem in docs?** Submit an improvement.

**Want to contribute?** See [CONTRIBUTING.md](../docs/CONTRIBUTING.md)
