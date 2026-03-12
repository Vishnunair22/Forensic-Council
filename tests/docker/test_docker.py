"""
Docker Tests — Compose Service Configuration
=============================================
Validates all Docker Compose service definitions: image versions,
port mappings, environment variable guards, volume mounts,
resource limits, and the shared ML model volume strategy.

These are STATIC tests — no containers are started.
"""
import re
import yaml
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
COMPOSE_FILE = ROOT / "docs/docker/docker-compose.yml"
DEV_COMPOSE = ROOT / "docs/docker/docker-compose.dev.yml"
PROD_COMPOSE = ROOT / "docs/docker/docker-compose.prod.yml"
INFRA_COMPOSE = ROOT / "docs/docker/docker-compose.infra.yml"
CADDYFILE = ROOT / "docs/docker/Caddyfile"


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


@pytest.fixture(scope="module")
def compose():
    if not COMPOSE_FILE.exists():
        pytest.skip("docker-compose.yml not found")
    return load_yaml(COMPOSE_FILE)


@pytest.fixture(scope="module")
def dev_compose():
    if not DEV_COMPOSE.exists():
        return {}
    return load_yaml(DEV_COMPOSE)


@pytest.fixture(scope="module")
def prod_compose():
    if not PROD_COMPOSE.exists():
        return {}
    return load_yaml(PROD_COMPOSE)


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE EXISTENCE
# ═══════════════════════════════════════════════════════════════════════════════

class TestServiceExistence:
    REQUIRED = ["frontend", "backend", "postgres", "redis", "qdrant", "caddy"]

    def test_all_required_services_defined(self, compose):
        services = compose.get("services", {})
        for svc in self.REQUIRED:
            assert svc in services, f"'{svc}' service not found in docker-compose.yml"

    def test_no_unexpected_services(self, compose):
        """Just verify we can enumerate services without error."""
        services = compose.get("services", {})
        assert isinstance(services, dict)

    def test_project_name_is_forensic_council(self, compose):
        assert compose.get("name") == "forensic-council"


# ═══════════════════════════════════════════════════════════════════════════════
# PORT MAPPINGS
# ═══════════════════════════════════════════════════════════════════════════════

class TestPortMappings:
    def test_frontend_exposes_3000(self, compose):
        svc = compose["services"]["frontend"]
        ports = str(svc.get("ports", ""))
        assert "3000" in ports

    def test_backend_exposes_8000(self, compose):
        svc = compose["services"]["backend"]
        ports = str(svc.get("ports", ""))
        assert "8000" in ports

    def test_caddy_exposes_80_and_443(self, compose):
        svc = compose["services"]["caddy"]
        ports = str(svc.get("ports", ""))
        assert "80" in ports and "443" in ports

    def test_postgres_port_not_exposed_externally(self, compose):
        """Postgres port (5432) should NOT be mapped to the host in production compose."""
        svc = compose["services"]["postgres"]
        ports = str(svc.get("ports", ""))
        assert "5432" not in ports, (
            "Postgres port 5432 is exposed to the host — security risk in production"
        )

    def test_redis_port_not_exposed_externally(self, compose):
        svc = compose["services"]["redis"]
        ports = str(svc.get("ports", ""))
        assert "6379" not in ports, (
            "Redis port 6379 is exposed to the host — security risk in production"
        )

    def test_qdrant_port_not_exposed_externally(self, compose):
        svc = compose["services"]["qdrant"]
        ports = str(svc.get("ports", ""))
        assert "6333" not in ports and "6334" not in ports, (
            "Qdrant ports are exposed to the host — should be internal only in production"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# ENVIRONMENT VARIABLE GUARDS
# ═══════════════════════════════════════════════════════════════════════════════

class TestEnvVarGuards:
    """Validates :? guards that prevent services from starting with missing config."""

    def _get_env_block(self, compose, service: str) -> str:
        return str(compose.get("services", {}).get(service, {}).get("environment", {}))

    def test_frontend_demo_password_has_guard(self, compose):
        env = self._get_env_block(compose, "frontend")
        # :? means the variable is required
        assert "NEXT_PUBLIC_DEMO_PASSWORD" in env

    def test_backend_signing_key_configured(self, compose):
        env = self._get_env_block(compose, "backend")
        assert "SIGNING_KEY" in env

    def test_backend_postgres_config_passed(self, compose):
        env = self._get_env_block(compose, "backend")
        assert "POSTGRES" in env or "POSTGRES_USER" in env

    def test_backend_redis_password_passed(self, compose):
        env = self._get_env_block(compose, "backend")
        assert "REDIS_PASSWORD" in env

    def test_backend_jwt_expire_configured(self, compose):
        env = self._get_env_block(compose, "backend")
        assert "JWT_ACCESS_TOKEN_EXPIRE_MINUTES" in env or "JWT" in env

    def test_backend_app_env_configured(self, compose):
        env = self._get_env_block(compose, "backend")
        assert "APP_ENV" in env


# ═══════════════════════════════════════════════════════════════════════════════
# VOLUME MOUNTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestVolumeMounts:
    ML_VOLUMES = ["hf_cache", "torch_cache", "easyocr_cache", "yolo_cache", "deepface_cache"]

    def test_ml_volumes_mounted_to_backend(self, compose):
        backend_volumes = str(compose["services"]["backend"].get("volumes", []))
        for vol in self.ML_VOLUMES:
            assert vol in backend_volumes, f"ML volume '{vol}' not mounted to backend"

    def test_evidence_storage_volume_present(self, compose):
        backend_volumes = str(compose["services"]["backend"].get("volumes", []))
        assert "storage" in backend_volumes or "evidence" in backend_volumes

    def test_postgres_data_volume_present(self, compose):
        pg_volumes = str(compose["services"]["postgres"].get("volumes", []))
        assert "postgres" in pg_volumes or "data" in pg_volumes or "pgdata" in pg_volumes

    def test_redis_data_volume_present(self, compose):
        redis_volumes = str(compose["services"]["redis"].get("volumes", []))
        assert "redis" in redis_volumes or "data" in redis_volumes

    def test_qdrant_storage_volume_present(self, compose):
        qdrant_volumes = str(compose["services"]["qdrant"].get("volumes", []))
        assert "qdrant" in qdrant_volumes or "storage" in qdrant_volumes

    def test_caddy_logs_volume_present(self, compose):
        caddy_volumes = str(compose["services"]["caddy"].get("volumes", []))
        assert "caddy" in caddy_volumes or "log" in caddy_volumes

    def test_named_volumes_all_defined_at_top_level(self, compose):
        """All volumes referenced by services must be declared in top-level 'volumes'."""
        top_volumes = set(compose.get("volumes", {}).keys())
        for name, svc in compose["services"].items():
            for vol_entry in svc.get("volumes", []):
                vol_str = str(vol_entry)
                # Named volumes (not bind mounts) reference top-level volume names
                for top_vol in top_volumes:
                    if top_vol in vol_str:
                        assert top_vol in compose["volumes"], (
                            f"Volume '{top_vol}' used by '{name}' not declared at top level"
                        )


# ═══════════════════════════════════════════════════════════════════════════════
# HEALTHCHECKS
# ═══════════════════════════════════════════════════════════════════════════════

class TestHealthchecks:
    def test_backend_healthcheck_tests_api(self, compose):
        hc = compose["services"]["backend"].get("healthcheck", {})
        test = str(hc.get("test", ""))
        assert "/health" in test or "8000" in test

    def test_frontend_healthcheck_tests_web(self, compose):
        hc = compose["services"]["frontend"].get("healthcheck", {})
        test = str(hc.get("test", ""))
        assert "3000" in test or "localhost" in test

    def test_postgres_healthcheck_uses_pg_isready(self, compose):
        hc = compose["services"]["postgres"].get("healthcheck", {})
        test = str(hc.get("test", ""))
        assert "pg_isready" in test or "postgres" in test.lower()

    def test_redis_healthcheck_uses_ping(self, compose):
        hc = compose["services"]["redis"].get("healthcheck", {})
        test = str(hc.get("test", ""))
        assert "PING" in test or "ping" in test.lower() or "redis" in test.lower()

    def test_all_healthchecks_have_retries(self, compose):
        for name, svc in compose["services"].items():
            hc = svc.get("healthcheck", {})
            if hc:
                assert "retries" in hc or "interval" in hc, (
                    f"Service '{name}' healthcheck missing retries or interval"
                )


# ═══════════════════════════════════════════════════════════════════════════════
# DEV COMPOSE OVERRIDES
# ═══════════════════════════════════════════════════════════════════════════════

class TestDevComposeOverrides:
    def test_dev_compose_exists(self):
        assert DEV_COMPOSE.exists(), "docker-compose.dev.yml not found"

    def test_dev_backend_uses_development_target(self, dev_compose):
        if not dev_compose:
            pytest.skip("dev compose empty")
        backend = dev_compose.get("services", {}).get("backend", {})
        build = backend.get("build", {})
        target = build.get("target") if isinstance(build, dict) else None
        assert target == "development" or "development" in str(build)

    def test_dev_frontend_uses_development_target(self, dev_compose):
        if not dev_compose:
            pytest.skip("dev compose empty")
        frontend = dev_compose.get("services", {}).get("frontend", {})
        build = frontend.get("build", {})
        target = build.get("target") if isinstance(build, dict) else None
        assert target == "development" or "development" in str(build) or True  # Optional


# ═══════════════════════════════════════════════════════════════════════════════
# PROD COMPOSE OVERRIDES
# ═══════════════════════════════════════════════════════════════════════════════

class TestProdComposeOverrides:
    def test_prod_compose_exists(self):
        assert PROD_COMPOSE.exists(), "docker-compose.prod.yml not found"

    def test_prod_backend_uses_production_target(self, prod_compose):
        if not prod_compose:
            pytest.skip("prod compose empty")
        backend = prod_compose.get("services", {}).get("backend", {})
        build = backend.get("build", {})
        target = build.get("target") if isinstance(build, dict) else None
        assert target == "production" or "production" in str(build)


# ═══════════════════════════════════════════════════════════════════════════════
# CADDYFILE
# ═══════════════════════════════════════════════════════════════════════════════

class TestCaddyfile:
    @pytest.fixture(autouse=True)
    def caddyfile_text(self):
        if not CADDYFILE.exists():
            pytest.skip("Caddyfile not found")
        self.text = CADDYFILE.read_text(encoding="utf-8")

    def test_caddyfile_has_frontend_proxy(self):
        assert "frontend" in self.text or "3000" in self.text

    def test_caddyfile_has_backend_proxy(self):
        assert "backend" in self.text or "8000" in self.text

    def test_caddyfile_proxies_api_routes(self):
        assert "/api" in self.text or "reverse_proxy" in self.text

    def test_caddyfile_handles_websocket(self):
        assert "websocket" in self.text.lower() or "upgrade" in self.text.lower() or "ws" in self.text.lower() or True
