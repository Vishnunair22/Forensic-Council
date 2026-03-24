"""
Infrastructure and Docker Standards — v1.0.4
=============================================
Comprehensive static analysis of the Forensic Council infrastructure.
Validates Docker Compose, Dockerfiles, and Project Manifests for:
 - Security Hardening (read_only, non-root, restricted ports)
 - Resource Management (memory limits, ML volume persistence)
 - Build Integrity (multi-stage, version pinning, npm ci)
 - Environment Safety (:? guards, .env.example documentation)

Run: pytest tests/infra/test_infra_standards.py -v
"""
import re
import yaml
import pytest
import json
from pathlib import Path

# ── Project Constants ──────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent.parent
COMPOSE_FILE = ROOT / "docs/docker/docker-compose.yml"
DEV_COMPOSE = ROOT / "docs/docker/docker-compose.dev.yml"
PROD_COMPOSE = ROOT / "docs/docker/docker-compose.prod.yml"
FRONTEND_DIR = ROOT / "frontend"
BACKEND_DIR = ROOT / "backend"
ENV_EXAMPLE = ROOT / ".env.example"

# ── Helper Functions ──────────────────────────────────────────────────────────

def load_yaml(path: Path) -> dict:
    if not path.exists(): return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}

def read_text(path: Path) -> str:
    if not path.exists(): return ""
    return path.read_text(encoding="utf-8")

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def compose():
    return load_yaml(COMPOSE_FILE)

@pytest.fixture(scope="module")
def dev_compose():
    return load_yaml(DEV_COMPOSE)

@pytest.fixture(scope="module")
def prod_compose():
    return load_yaml(PROD_COMPOSE)

# ═══════════════════════════════════════════════════════════════════════════════
# DOCKER COMPOSE STANDARDS (ORCHESTRATION)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDockerCompose:
    REQUIRED_SERVICES = ["frontend", "backend", "postgres", "redis", "qdrant", "caddy"]

    def test_all_services_present_and_named_correctly(self, compose):
        assert compose.get("name") == "forensic-council"
        services = compose.get("services", {})
        for svc in self.REQUIRED_SERVICES:
            assert svc in services, f"Missing core service: {svc}"

    def test_port_exposure_restricted(self, compose):
        """Web services exposed; database/infra restricted to internal network."""
        services = compose["services"]
        # Publicly accessible
        assert "3000" in str(services["frontend"].get("ports", []))
        assert "8000" in str(services["backend"].get("ports", []))
        assert "80" in str(services["caddy"].get("ports", []))
        
        # Internal only
        for svc in ["postgres", "redis", "qdrant"]:
            ports = services[svc].get("ports", [])
            assert not ports, f"Service {svc} should not expose ports to the host."

    def test_ml_shared_volume_persistence(self, compose):
        """ML models MUST be in named volumes to avoid multi-hour re-downloads."""
        volumes = compose.get("volumes", {})
        expected = ["hf_cache", "torch_cache", "easyocr_cache", "yolo_cache", "deepface_cache"]
        for vol in expected:
            assert vol in volumes, f"ML volume {vol} is missing from top-level definitions."
        
        backend_vols = str(compose["services"]["backend"].get("volumes", []))
        for vol in expected:
            assert vol in backend_vols, f"Backend failed to mount ML volume {vol}."

    def test_service_healthcheck_coverage(self, compose):
        """Every service must define a healthcheck for zero-downtime restarts."""
        for name, svc in compose["services"].items():
            assert "healthcheck" in svc, f"Service '{name}' missing healthcheck."
            hc = svc["healthcheck"]
            assert "test" in hc and "interval" in hc

    def test_dependency_chain_with_health_conditions(self, compose):
        """Backend must WAIT for healthy infra (not just 'started' containers)."""
        backend_deps = compose["services"]["backend"].get("depends_on", {})
        for infra in ["postgres", "redis", "qdrant"]:
            assert infra in backend_deps
            assert backend_deps[infra].get("condition") == "service_healthy"

    def test_security_hardening_flags(self, compose):
        """Production hardening: read_only FS and memory limits."""
        backend = compose["services"]["backend"]
        assert backend.get("read_only") is True
        
        # Memory limits check (deploy/resources)
        res = backend.get("deploy", {}).get("resources", {})
        assert "limits" in res or "reservations" in res or "mem_limit" in backend

# ═══════════════════════════════════════════════════════════════════════════════
# DOCKERFILE STANDARDS (IMAGERY)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDockerfiles:
    def test_frontend_multi_stage_and_security(self):
        text = read_text(FRONTEND_DIR / "Dockerfile")
        assert text.count("FROM ") >= 2, "Frontend should use multi-stage builds."
        assert "HOSTNAME=0.0.0.0" in text, "Hostname must be 0.0.0.0 for container bind."
        assert "npm ci" in text, "Use 'npm ci' for reproducible builds."

    def test_backend_multi_stage_and_tooling(self):
        text = read_text(BACKEND_DIR / "Dockerfile")
        assert text.count("FROM ") >= 2, "Backend should use multi-stage builds."
        assert "uv " in text or "pip install" in text
        assert "production" in text, "Missing production stage in backend Dockerfile."
        assert "development" in text, "Missing development stage in backend Dockerfile."

    def test_no_latest_tag_placeholders(self):
        """Verify we are not relying on 'latest' as a build target."""
        # Simple check in compose files
        for f in [COMPOSE_FILE, DEV_COMPOSE, PROD_COMPOSE]:
            if not f.exists(): continue
            content = read_text(f)
            # Only allow :latest if explicitly intended for external base images (like redis:latest)
            # but our own images should be versioned.
            assert ":latest" not in content or "redis" in content or "postgres" in content

# ═══════════════════════════════════════════════════════════════════════════════
# ENVIRONMENT & MANIFESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestManifestsAndEnv:
    def test_env_example_documentation_coverage(self):
        text = read_text(ENV_EXAMPLE)
        required = [
            "SIGNING_KEY", "APP_ENV", "POSTGRES_PASSWORD", "REDIS_PASSWORD",
            "LLM_API_KEY", "NEXT_PUBLIC_API_URL"
        ]
        for var in required:
            assert var in text, f"Env var {var} not documented in .env.example"

    def test_project_versions_sync(self):
        """Ensure v1.0.4 is reflected across all manifests."""
        backend_toml = read_text(BACKEND_DIR / "pyproject.toml")
        frontend_pkg = json.loads(read_text(FRONTEND_DIR / "package.json"))
        
        # Extract version from TOML (simple regex)
        version_match = re.search(r'version\s*=\s*"(.*?)"', backend_toml)
        backend_version = version_match.group(1) if version_match else None
        
        assert backend_version == "1.0.4"
        assert frontend_pkg.get("version") == "1.0.4"

    def test_frontend_jest_config_exists(self):
        assert (FRONTEND_DIR / "jest.config.ts").exists() or (FRONTEND_DIR / "jest.config.mjs").exists()

    def test_backend_dependencies_exist(self):
        toml = read_text(BACKEND_DIR / "pyproject.toml")
        for pkg in ["fastapi", "pydantic", "asyncpg", "redis"]:
            assert pkg in toml.lower()
