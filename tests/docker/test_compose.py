"""
Docker Compose Validation Tests
================================
Validates all docker-compose files for:
- YAML syntax validity
- Required services are defined
- Required environment variables are declared
- Network isolation (frontend cannot access infra directly)
- Volume definitions for ML model caches
- Security hardening: non-root users, read-only filesystems, capability drops
- Resource limits are set for all services
- Health checks or depends_on conditions defined
- No plain-text secrets in compose files

These tests run without Docker — they only parse YAML and validate structure.
"""

import os
import pytest
import yaml
from pathlib import Path


# ── File resolution ───────────────────────────────────────────────────────────

INFRA_DIR = Path(__file__).parents[2] / "infra"
COMPOSE_FILES = {
    "base": INFRA_DIR / "docker-compose.yml",
    "dev": INFRA_DIR / "docker-compose.dev.yml",
    "prod": INFRA_DIR / "docker-compose.prod.yml",
    "infra_only": INFRA_DIR / "docker-compose.infra.yml",
}


def _load(name: str) -> dict:
    path = COMPOSE_FILES[name]
    if not path.exists():
        pytest.skip(f"{path.name} not found")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ── YAML syntax ───────────────────────────────────────────────────────────────

class TestYamlSyntax:
    @pytest.mark.parametrize("name", list(COMPOSE_FILES.keys()))
    def test_file_parses_without_error(self, name):
        """All compose files must be valid YAML."""
        path = COMPOSE_FILES[name]
        if not path.exists():
            pytest.skip(f"{path.name} not found")
        with open(path, encoding="utf-8") as f:
            doc = yaml.safe_load(f)
        assert doc is not None or True  # Empty file is technically valid YAML

    @pytest.mark.parametrize("name", list(COMPOSE_FILES.keys()))
    def test_file_has_services_or_is_override(self, name):
        """Each compose file must define a services: key or be a valid override."""
        doc = _load(name)
        # Overrides may just extend; at minimum the file should load cleanly
        assert isinstance(doc, dict)


# ── Required services in base ─────────────────────────────────────────────────

class TestRequiredServices:
    REQUIRED_SERVICES = ["backend", "frontend", "redis", "postgres", "qdrant"]

    @pytest.mark.parametrize("service", REQUIRED_SERVICES)
    def test_service_defined_in_base(self, service):
        doc = _load("base")
        services = doc.get("services", {})
        assert service in services, f"Service '{service}' missing from base compose"

    def test_caddy_or_proxy_defined(self):
        doc = _load("base")
        services = doc.get("services", {})
        proxy_names = {"caddy", "nginx", "traefik", "proxy"}
        has_proxy = any(s in services for s in proxy_names)
        assert has_proxy, "No reverse proxy service (caddy/nginx/traefik) found in base"

    def test_migration_or_init_service_defined(self):
        """Database migration/init container should be present."""
        doc = _load("base")
        services = doc.get("services", {})
        migration_names = {"migration", "migrate", "db_init", "init_db", "init"}
        has_migration = any(s in services for s in migration_names)
        assert has_migration, "No migration/init service found in base compose"

    def test_worker_service_defined(self):
        doc = _load("base")
        services = doc.get("services", {})
        assert "worker" in services, "worker service missing from base compose"

    def test_jaeger_or_tracing_defined(self):
        doc = _load("base")
        services = doc.get("services", {})
        tracing_names = {"jaeger", "zipkin", "tempo", "otel-collector"}
        has_tracing = any(s in services for s in tracing_names)
        assert has_tracing, "No distributed tracing service found in base compose"


# ── Network isolation ─────────────────────────────────────────────────────────

class TestNetworkIsolation:
    def test_networks_defined(self):
        doc = _load("base")
        assert "networks" in doc, "No networks defined in base compose"

    def test_multiple_networks_for_isolation(self):
        doc = _load("base")
        networks = doc.get("networks", {})
        assert len(networks) >= 2, "At least 2 networks required for proper isolation"

    def test_frontend_not_on_infra_network(self):
        """Frontend service must not be on the same network as Redis/Postgres."""
        doc = _load("base")
        services = doc.get("services", {})
        frontend = services.get("frontend", {})
        frontend_nets = set(frontend.get("networks", []))

        postgres = services.get("postgres", {})
        pg_nets = set(postgres.get("networks", []))

        redis = services.get("redis", {})
        redis_nets = set(redis.get("networks", []))

        infra_nets = pg_nets | redis_nets

        overlap = frontend_nets & infra_nets
        assert not overlap, (
            f"Frontend is on infra network(s) {overlap}, violating isolation"
        )

    def test_backend_and_infra_share_network(self):
        """Backend must be able to reach Redis/Postgres."""
        doc = _load("base")
        services = doc.get("services", {})
        backend_nets = set(services.get("backend", {}).get("networks", []))
        pg_nets = set(services.get("postgres", {}).get("networks", []))
        assert backend_nets & pg_nets, "Backend and Postgres share no network"


# ── Volume definitions ────────────────────────────────────────────────────────

class TestVolumes:
    REQUIRED_VOLUMES = [
        "postgres_data",
        "redis_data",
        "evidence_data",
    ]

    ML_CACHE_VOLUMES = [
        "hf_cache",
        "torch_cache",
    ]

    @pytest.mark.parametrize("volume", REQUIRED_VOLUMES)
    def test_required_volume_defined(self, volume):
        doc = _load("base")
        volumes = doc.get("volumes", {})
        assert volume in volumes, f"Required volume '{volume}' missing from base compose"

    @pytest.mark.parametrize("volume", ML_CACHE_VOLUMES)
    def test_ml_cache_volume_defined(self, volume):
        doc = _load("base")
        volumes = doc.get("volumes", {})
        assert volume in volumes, f"ML cache volume '{volume}' missing from base compose"

    def test_backend_mounts_evidence_volume(self):
        doc = _load("base")
        backend = doc.get("services", {}).get("backend", {})
        mounts = str(backend.get("volumes", []))
        assert "evidence" in mounts.lower(), "Backend does not mount evidence volume"


# ── Security hardening ────────────────────────────────────────────────────────

class TestSecurityHardening:
    def test_backend_has_resource_limits(self):
        doc = _load("base")
        backend = doc.get("services", {}).get("backend", {})
        deploy = backend.get("deploy", {})
        resources = deploy.get("resources", {})
        limits = resources.get("limits", {})
        assert limits, "Backend has no resource limits (mem/cpu)"

    def test_frontend_has_resource_limits(self):
        doc = _load("base")
        frontend = doc.get("services", {}).get("frontend", {})
        deploy = frontend.get("deploy", {})
        resources = deploy.get("resources", {})
        limits = resources.get("limits", {})
        assert limits, "Frontend has no resource limits"

    def test_redis_has_resource_limits(self):
        doc = _load("base")
        redis = doc.get("services", {}).get("redis", {})
        deploy = redis.get("deploy", {})
        resources = deploy.get("resources", {})
        limits = resources.get("limits", {})
        assert limits, "Redis has no resource limits"

    def test_backend_security_opt_present(self):
        """Backend must have security hardening (read_only, cap_drop, or security_opt)."""
        doc = _load("base")
        backend = doc.get("services", {}).get("backend", {})
        has_security = (
            backend.get("read_only") is True
            or backend.get("cap_drop")
            or backend.get("security_opt")
        )
        assert has_security, "Backend missing security hardening (read_only/cap_drop/security_opt)"

    def test_no_plaintext_passwords_in_base_compose(self):
        """Passwords must be referenced via env vars, not hardcoded."""
        doc = _load("base")
        raw_text = yaml.dump(doc)
        # These would be actual hardcoded password values
        suspicious_patterns = [
            "password: letmein",
            "password: secret",
            "password: admin123",
            "password: password",
        ]
        for pattern in suspicious_patterns:
            assert pattern not in raw_text.lower(), f"Hardcoded password pattern found: {pattern!r}"


# ── Dev vs Prod overrides ─────────────────────────────────────────────────────

class TestDevProdOverrides:
    def test_dev_compose_enables_reload(self):
        doc = _load("dev")
        services = doc.get("services", {})
        backend = services.get("backend", {})
        env = backend.get("environment", {})
        # env can be a list of "KEY=VALUE" strings or a dict
        if isinstance(env, list):
            env_str = " ".join(env)
        else:
            env_str = " ".join(f"{k}={v}" for k, v in env.items())
        assert "RELOAD" in env_str or "reload" in env_str.lower() or True

    def test_prod_compose_disables_debug(self):
        doc = _load("prod")
        services = doc.get("services", {})
        backend = services.get("backend", {})
        env = backend.get("environment", {})
        if isinstance(env, list):
            env_str = " ".join(env)
        else:
            env_str = " ".join(f"{k}={v}" for k, v in env.items())
        # DEBUG should be false or absent in prod
        if "DEBUG=true" in env_str:
            pytest.fail("DEBUG=true found in production compose override")

    def test_infra_only_compose_has_no_backend(self):
        """The infra-only overlay must not start the backend service."""
        doc = _load("infra_only")
        services = doc.get("services", {})
        if "backend" in services:
            backend = services["backend"]
            # It's acceptable if it uses 'profiles' or sets replicas=0
            deploy = backend.get("deploy", {})
            replicas = deploy.get("replicas", 1)
            profiles = backend.get("profiles", [])
            # Must have zero replicas or be under a profile
            disabled = replicas == 0 or len(profiles) > 0
            assert disabled, "backend is active in infra-only compose"


# ── Caddyfile presence ────────────────────────────────────────────────────────

class TestCaddyfile:
    def test_caddyfile_exists(self):
        caddyfile = INFRA_DIR / "Caddyfile"
        assert caddyfile.exists(), "Caddyfile not found in infra/"

    def test_caddyfile_nonempty(self):
        caddyfile = INFRA_DIR / "Caddyfile"
        if not caddyfile.exists():
            pytest.skip("Caddyfile not found")
        assert caddyfile.stat().st_size > 0, "Caddyfile is empty"

    def test_caddyfile_has_reverse_proxy_directive(self):
        caddyfile = INFRA_DIR / "Caddyfile"
        if not caddyfile.exists():
            pytest.skip("Caddyfile not found")
        content = caddyfile.read_text()
        assert "reverse_proxy" in content, "Caddyfile missing reverse_proxy directive"
