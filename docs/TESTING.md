# Testing Guide

The Forensic Council relies on `pytest` for the backend and `jest` for the frontend. 

For the complete list of available test suites and coverage reports, please refer to `FORENSIC_COUNCIL_TEST_SUITE.md`. This document explains **how** to execute them.

## 1. Local Backend Testing

The backend relies on Postgres, Redis, and Qdrant to function. Therefore, the testing environment uses Docker containers.

### A. Spin up dependent services

Instead of starting the full stack, start only the data stores:
```bash
docker compose -f docker-compose.infra.yml up -d
```

### B. Setup Python Virtual Environment

Ensure `uv` is installed, then create a test environment inside `backend/`:
```bash
cd backend
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e ".[test]"
```

### C. Run the Pytest Suite

```bash
# Run all tests
pytest

# Run tests with stdout output and debug logs
pytest -s -v

# Run only a specific test file
pytest tests/unit/test_ml_subprocess.py

# Generate a coverage report
pytest --cov=core --cov=agents --cov=orchestration --cov-report=html
```

You can view the coverage report by opening `backend/htmlcov/index.html` in your browser.

## 2. Local Frontend Testing

The Next.js frontend utilizes `jest` and React Testing Library for simulating UI states.

### A. Run Jest Tests

```bash
cd frontend
npm install

# Run all tests
npm run test

# Run tests in watch mode (ideal for active development)
npm run test:watch
```

## 3. Continuous Integration (CI)

Our system expects both backend and frontend tests to pass before merging any Pull Requests.
Currently, a PR requires:
*   A minimum of **85% backend line coverage**.
*   All tests marked `@pytest.mark.asyncio` must pass securely without hanging the event loop.
*   No frontend linting errors (`npm run lint`).
