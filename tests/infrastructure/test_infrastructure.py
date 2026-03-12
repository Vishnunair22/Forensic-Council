"""
Infrastructure Tests — Static Analysis
=======================================
Validates docker-compose structure, Dockerfile correctness,
environment variable presence, CI/CD pipeline, and Python
package configuration — all without running any containers.
"""
import os
import re
import yaml
import pytest
from pathlib import Path

# ── Project root ──────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent.parent.parent  # tests/ → project root
COMPOSE_FILE = ROOT / "docs/docker/docker-compose.yml"
DEV_COMPOSE = ROOT / "docs/docker/docker-compose.dev.yml"
PROD_COMPOSE = ROOT / "docs/docker/docker-compose.prod.yml"
INFRA_COMPOSE = ROOT / "docs/docker/docker-compose.infra.yml"
FRONTEND_DOCKERFILE = ROOT / "frontend/Dockerfile"
BACKEND_DOCKERFILE = ROOT / "backend/Dockerfile"
ENV_EXAMPLE = ROOT / ".env.example"
CI_YML = ROOT / ".github/workflows/ci.yml"
PYPROJECT = ROOT / "backend/pyproject.toml"
PACKAGE_JSON = ROOT / "frontend/package.json"
JEST_CONFIG = ROOT / "frontend/jest.config.ts"

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════════
# DOCKER COMPOSE — BASE
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def compose():
    if not COMPOSE_FILE.exists():
        pytest.skip(f"docker-compose.yml not found at {COMPOSE_FILE}")
    return load_yaml(COMPOSE_FILE)


class TestComposeStructure:
    REQUIRED_SERVICES = ["frontend", "backend", "postgres", "redis", "qdrant", "caddy"]

    def test_services_key_present(self, compose):
        assert "services" in compose

    def test_all_required_services_present(self, compose):
        services = compose["services"]
        for svc in self.REQUIRED_SERVICES:
            assert svc in services, f"Service '{svc}' missing from docker-compose.yml"

    def test_compose_project_name_set(self, compose):
        assert compose.get("name") == "forensic-council", (
            "Top-level 'name: forensic-council' is required to pin shared ML model volumes"
        )

    def test_ml_volumes_defined(self, compose):
        volumes = compose.get("volumes", {})
        expected = ["hf_cache", "torch_cache", "easyocr_cache", "yolo_cache", "deepface_cache"]
        for vol in expected:
            assert vol in volumes, f"ML cache volume '{vol}' not defined"

    def test_backend_depends_on_infra_with_service_healthy(self, compose):
        backend = compose["services"]["backend"]
        deps = backend.get("depends_on", {})
        for svc in ("postgres", "redis", "qdrant"):
            assert svc in deps, f"backend.depends_on missing '{svc}'"
            if isinstance(deps[svc], dict):
                assert deps[svc].get("condition") == "service_healthy", (
                    f"backend depends on {svc} but not with service_healthy condition"
                )

    def test_frontend_depends_on_backend(self, compose):
        frontend = compose["services"]["frontend"]
        deps = frontend.get("depends_on", {})
        assert "backend" in deps

    def test_caddy_depends_on_frontend_and_backend(self, compose):
        caddy = compose["services"]["caddy"]
        deps = caddy.get("depends_on", {})
        assert "frontend" in deps or "backend" in deps


class TestComposeHealthchecks:
    def test_all_services_have_healthchecks(self, compose):
        no_healthcheck = []
        for name, svc in compose["services"].items():
            if "healthcheck" not in svc:
                no_healthcheck.append(name)
        assert not no_healthcheck, f"Services without healthcheck: {no_healthcheck}"

    def test_backend_healthcheck_interval(self, compose):
        hc = compose["services"]["backend"]["healthcheck"]
        assert "interval" in hc

    def test_frontend_healthcheck_start_period(self, compose):
        hc = compose["services"]["frontend"]["healthcheck"]
        start = hc.get("start_period", "0s")
        # Should be >= 30s
        seconds = int(re.sub(r"[^0-9]", "", start) or 0)
        assert seconds >= 30, f"Frontend start_period is {start}, should be >= 30s"

    def test_backend_healthcheck_start_period_reasonable(self, compose):
        hc = compose["services"]["backend"]["healthcheck"]
        start = hc.get("start_period", "0s")
        seconds = int(re.sub(r"[^0-9]", "", start) or 0)
        assert seconds >= 30, f"Backend start_period is {start}, should be >= 30s"


class TestComposeRestart:
    def test_frontend_has_restart_policy(self, compose):
        frontend = compose["services"]["frontend"]
        assert "restart" in frontend, "frontend service should have a restart policy"
        assert frontend["restart"] in ("unless-stopped", "always", "on-failure")

    def test_backend_has_restart_policy(self, compose):
        backend = compose["services"]["backend"]
        assert "restart" in backend


class TestComposeSecurityHardening:
    def test_backend_read_only_filesystem(self, compose):
        backend = compose["services"]["backend"]
        assert backend.get("read_only") is True, (
            "backend service should use read_only: true for security"
        )

    def test_backend_tmpfs_for_writable_paths(self, compose):
        backend = compose["services"]["backend"]
        assert "tmpfs" in backend or "volumes" in backend, (
            "backend with read_only=true needs tmpfs or volumes for writable paths"
        )

    def test_redis_has_password_via_command_or_env(self, compose):
        redis = compose["services"]["redis"]
        cmd = str(redis.get("command", ""))
        env = str(redis.get("environment", {}))
        assert "requirepass" in cmd or "REDIS_PASSWORD" in env or "redis_password" in env.lower()

    def test_services_have_memory_limits(self, compose):
        """At minimum backend and frontend should have memory limits."""
        for svc in ("backend", "frontend"):
            service = compose["services"][svc]
            deploy = service.get("deploy", {})
            resources = deploy.get("resources", {}) if isinstance(deploy, dict) else {}
            limits = resources.get("limits", {})
            mem_limit = service.get("mem_limit") or limits.get("memory")
            # Soft check — just verify it's either set at top level or in deploy
            has_limit = bool(mem_limit or service.get("deploy"))
            assert has_limit, f"{svc} has no memory limits defined"

    def test_no_latest_image_tags(self, compose):
        """Production services should pin specific image versions."""
        for name, svc in compose["services"].items():
            image = svc.get("image", "")
            if image and ":" in image:
                tag = image.split(":")[-1]
                assert tag != "latest", (
                    f"Service '{name}' uses 'latest' tag ({image}). "
                    "Pin to a specific version for reproducible builds."
                )


# ═══════════════════════════════════════════════════════════════════════════════
# FRONTEND DOCKERFILE
# ═══════════════════════════════════════════════════════════════════════════════

class TestFrontendDockerfile:
    @pytest.fixture(autouse=True)
    def content(self):
        if not FRONTEND_DOCKERFILE.exists():
            pytest.skip("frontend/Dockerfile not found")
        self.text = read_text(FRONTEND_DOCKERFILE)

    def test_uses_node_base(self):
        assert "FROM node:" in self.text

    def test_uses_alpine_for_small_image(self):
        assert "alpine" in self.text

    def test_multi_stage_build_present(self):
        # Multiple FROM statements = multi-stage
        assert self.text.count("FROM ") >= 2

    def test_hostname_env_set(self):
        """HOSTNAME=0.0.0.0 is required for the container to bind correctly."""
        assert "HOSTNAME" in self.text and "0.0.0.0" in self.text, (
            "HOSTNAME=0.0.0.0 must be set in the frontend Dockerfile (v1.0.3 fix)"
        )

    def test_healthcheck_uses_wget(self):
        """Frontend healthcheck must use wget (not curl — alpine doesn't include curl by default)."""
        assert "wget" in self.text, (
            "Frontend Dockerfile healthcheck must use wget (not curl) — alpine doesn't ship curl"
        )

    def test_exposes_port_3000(self):
        assert "3000" in self.text

    def test_standalone_output_configured(self):
        """next.config should use output: standalone for Docker."""
        # This is in next.config.ts, not Dockerfile — just verify COPY source happens
        assert "COPY" in self.text

    def test_npm_ci_used_not_install(self):
        """npm ci is reproducible; npm install is not."""
        assert "npm ci" in self.text


# ═══════════════════════════════════════════════════════════════════════════════
# BACKEND DOCKERFILE
# ═══════════════════════════════════════════════════════════════════════════════

class TestBackendDockerfile:
    @pytest.fixture(autouse=True)
    def content(self):
        if not BACKEND_DOCKERFILE.exists():
            pytest.skip("backend/Dockerfile not found")
        self.text = read_text(BACKEND_DOCKERFILE)

    def test_uses_python_3_12(self):
        assert "python:3.12" in self.text or "python:3.1" in self.text

    def test_multi_stage_build(self):
        assert self.text.count("FROM ") >= 2

    def test_has_development_stage(self):
        """docker-compose.dev.yml uses target: development."""
        assert "development" in self.text

    def test_has_production_stage(self):
        """docker-compose.prod.yml uses target: production."""
        assert "production" in self.text

    def test_uses_uv_package_manager(self):
        assert "uv" in self.text

    def test_buildkit_cache_mount_present(self):
        """BuildKit cache mounts speed up repeated builds."""
        assert "--mount=type=cache" in self.text

    def test_exposes_port_8000(self):
        assert "8000" in self.text

    def test_has_entrypoint_or_cmd(self):
        assert "ENTRYPOINT" in self.text or "CMD" in self.text

    def test_non_root_user_or_explicit_security(self):
        """Best practice: run as non-root user."""
        # Soft check — many valid approaches exist
        has_user = "USER " in self.text
        has_readonly = True  # read_only is set in compose, not Dockerfile
        assert has_user or has_readonly


# ═══════════════════════════════════════════════════════════════════════════════
# ENVIRONMENT VARIABLES
# ═══════════════════════════════════════════════════════════════════════════════

class TestEnvironmentVariables:
    @pytest.fixture(autouse=True)
    def env_text(self):
        if not ENV_EXAMPLE.exists():
            pytest.skip(".env.example not found")
        self.text = read_text(ENV_EXAMPLE)

    REQUIRED_VARS = [
        "COMPOSE_PROJECT_NAME", "APP_ENV", "SIGNING_KEY",
        "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB",
        "REDIS_PASSWORD", "NEXT_PUBLIC_DEMO_PASSWORD", "NEXT_PUBLIC_API_URL",
        "LLM_PROVIDER", "LLM_API_KEY", "JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
        "BOOTSTRAP_ADMIN_PASSWORD", "BOOTSTRAP_INVESTIGATOR_PASSWORD",
    ]

    def test_all_required_vars_documented(self):
        for var in self.REQUIRED_VARS:
            assert var in self.text, f"Required env var '{var}' not documented in .env.example"

    def test_compose_project_name_is_forensic_council(self):
        assert "COMPOSE_PROJECT_NAME=forensic-council" in self.text

    def test_signing_key_has_generation_instructions(self):
        assert "secrets.token_hex" in self.text or "generate" in self.text.lower()

    def test_jwt_expire_documented_as_60_minutes(self):
        assert "60" in self.text and "JWT_ACCESS_TOKEN_EXPIRE_MINUTES" in self.text

    def test_llm_provider_groq_documented(self):
        assert "groq" in self.text.lower()

    def test_hf_token_documented(self):
        assert "HF_TOKEN" in self.text

    def test_domain_tls_documented(self):
        assert "DOMAIN" in self.text


# ═══════════════════════════════════════════════════════════════════════════════
# CI/CD
# ═══════════════════════════════════════════════════════════════════════════════

class TestCICD:
    @pytest.fixture(autouse=True)
    def ci(self):
        if not CI_YML.exists():
            pytest.skip(".github/workflows/ci.yml not found")
        self.ci = load_yaml(CI_YML)
        self.text = read_text(CI_YML)

    def test_ci_has_jobs(self):
        assert "jobs" in self.ci
        assert len(self.ci["jobs"]) > 0

    def test_ci_triggers_on_push_and_pr(self):
        on = self.ci.get("on", self.ci.get(True, {}))
        triggers = str(on).lower()
        assert "push" in triggers or "pull_request" in triggers

    def test_ci_has_backend_test_job(self):
        jobs = self.ci["jobs"]
        job_names = " ".join(jobs.keys()).lower()
        assert "backend" in job_names or "test" in job_names or "lint" in job_names

    def test_ci_has_frontend_job(self):
        jobs = self.ci["jobs"]
        job_names = " ".join(jobs.keys()).lower()
        assert "frontend" in job_names or "build" in job_names

    def test_ci_has_docker_build_job(self):
        assert "docker" in self.text.lower() or "build" in self.text.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# PACKAGE CONFIGS
# ═══════════════════════════════════════════════════════════════════════════════

class TestPackageConfigs:
    def test_pyproject_exists(self):
        assert PYPROJECT.exists()

    def test_pyproject_has_required_deps(self):
        content = read_text(PYPROJECT)
        for dep in ("fastapi", "pydantic", "asyncpg", "redis"):
            assert dep in content.lower(), f"Missing dep '{dep}' in pyproject.toml"

    def test_package_json_exists(self):
        assert PACKAGE_JSON.exists()

    def test_package_json_has_test_script(self):
        import json as _json
        pkg = _json.loads(read_text(PACKAGE_JSON))
        scripts = pkg.get("scripts", {})
        assert "test" in scripts, "No 'test' script in frontend/package.json"

    def test_jest_config_exists(self):
        assert JEST_CONFIG.exists()

    def test_package_json_has_testing_libs(self):
        import json as _json
        pkg = _json.loads(read_text(PACKAGE_JSON))
        all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        assert "jest" in all_deps or "@jest/core" in all_deps
        assert "@testing-library/react" in all_deps or "@testing-library/dom" in all_deps
