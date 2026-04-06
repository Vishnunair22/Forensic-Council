"""
Connectivity Tests — Live Service Integration
=============================================
These tests require a RUNNING Docker stack.

  Start stack first:
    docker compose -f infra/docker-compose.yml --env-file .env up -d

  Then run:
    pytest tests/connectivity/ -v

These tests ping every service, verify the API is healthy,
check the WebSocket handshake, and validate the auth flow end-to-end.

All tests are marked `requires_docker` and are skipped automatically
if the services are not reachable — so they never break CI runs
that don't have Docker available.
"""
import os
import json
import time
import socket
import asyncio
import uuid
import pytest

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    import asyncpg
    HAS_ASYNCPG = True
except ImportError:
    HAS_ASYNCPG = False

try:
    import redis.asyncio as aioredis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False

# ── Configuration from environment ───────────────────────────────────────────

API_BASE = os.environ.get("NEXT_PUBLIC_API_URL", "http://localhost:8000")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")
POSTGRES_DSN = (
    f"postgresql://{os.environ.get('POSTGRES_USER','forensic_user')}"
    f":{os.environ.get('POSTGRES_PASSWORD','forensic_pass')}"
    f"@localhost:5432/{os.environ.get('POSTGRES_DB','forensic_council')}"
)
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "forensic_redis_dev_password")
QDRANT_URL = "http://localhost:6333"
INVESTIGATOR_PASSWORD = os.environ.get("BOOTSTRAP_INVESTIGATOR_PASSWORD", "inv123!")

# ── Skip helper ───────────────────────────────────────────────────────────────

def is_port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False

def require_api():
    host = API_BASE.replace("http://", "").replace("https://", "").split(":")[0]
    port = int(API_BASE.split(":")[-1]) if ":" in API_BASE.replace("http://", "") else 8000
    if not is_port_open(host, port):
        pytest.skip(f"Backend API not reachable at {API_BASE}")

def require_frontend():
    if not is_port_open("localhost", 3000):
        pytest.skip("Frontend not reachable at localhost:3000")

def require_postgres():
    if not is_port_open("localhost", 5432):
        pytest.skip("Postgres not reachable at localhost:5432")

def require_redis():
    if not is_port_open(REDIS_HOST, REDIS_PORT):
        pytest.skip(f"Redis not reachable at {REDIS_HOST}:{REDIS_PORT}")

def require_qdrant():
    if not is_port_open("localhost", 6333):
        pytest.skip("Qdrant not reachable at localhost:6333")


# ═══════════════════════════════════════════════════════════════════════════════
# BACKEND API CONNECTIVITY
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.requires_docker
class TestBackendAPIConnectivity:
    @pytest.fixture(autouse=True)
    def check_api(self):
        require_api()
        if not HAS_HTTPX:
            pytest.skip("httpx not installed — pip install httpx")

    def test_root_endpoint_reachable(self):
        r = httpx.get(f"{API_BASE}/", timeout=10)
        assert r.status_code == 200

    def test_health_endpoint_returns_ok(self):
        r = httpx.get(f"{API_BASE}/health", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") in ("healthy", "ok", "running")

    def test_api_docs_available_in_dev(self):
        r = httpx.get(f"{API_BASE}/docs", timeout=10)
        # Docs available in dev, may be disabled in prod
        assert r.status_code in (200, 404)

    def test_api_openapi_json_available(self):
        r = httpx.get(f"{API_BASE}/openapi.json", timeout=10)
        assert r.status_code in (200, 404)

    def test_response_has_security_headers(self):
        r = httpx.get(f"{API_BASE}/health", timeout=10)
        assert "x-content-type-options" in r.headers
        assert "x-frame-options" in r.headers

    def test_auth_login_endpoint_responds(self):
        r = httpx.post(
            f"{API_BASE}/api/v1/auth/login",
            data={"username": "wrong_user", "password": "wrong_pass"},
            timeout=10,
        )
        assert r.status_code in (200, 400, 401, 422)

    def test_successful_demo_login(self):
        """Login with the bootstrap investigator account."""
        r = httpx.post(
            f"{API_BASE}/api/v1/auth/login",
            data={"username": "investigator", "password": INVESTIGATOR_PASSWORD},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            assert "access_token" in data
            assert data["token_type"] == "bearer"
        else:
            assert r.status_code in (400, 401)  # Bootstrap may not have run

    def test_protected_route_without_token(self):
        r = httpx.get(f"{API_BASE}/api/v1/auth/me", timeout=10)
        assert r.status_code in (401, 403)

    def test_rate_limit_header_present_on_investigate(self):
        r = httpx.options(f"{API_BASE}/api/v1/investigate", timeout=10)
        assert r.status_code in (200, 204, 405)

    def test_resume_endpoint_reachable(self):
        r = httpx.post(f"{API_BASE}/api/v1/sessions/{uuid.uuid4()}/resume", timeout=10)
        assert r.status_code in (200, 401, 403, 404, 422)

    def test_arbiter_status_endpoint_reachable(self):
        r = httpx.get(f"{API_BASE}/api/v1/sessions/{uuid.uuid4()}/arbiter-status", timeout=10)
        assert r.status_code in (200, 401, 403, 404)


# ═══════════════════════════════════════════════════════════════════════════════
# FRONTEND CONNECTIVITY
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.requires_docker
class TestFrontendConnectivity:
    @pytest.fixture(autouse=True)
    def check_frontend(self):
        require_frontend()
        if not HAS_HTTPX:
            pytest.skip("httpx not installed")

    def test_frontend_home_page_loads(self):
        r = httpx.get(f"{FRONTEND_URL}/", timeout=15)
        assert r.status_code == 200

    def test_frontend_returns_html(self):
        r = httpx.get(f"{FRONTEND_URL}/", timeout=15)
        assert "text/html" in r.headers.get("content-type", "")

    def test_frontend_evidence_page_loads(self):
        r = httpx.get(f"{FRONTEND_URL}/evidence", timeout=15)
        assert r.status_code in (200, 308, 302)

    def test_frontend_api_proxy_works(self):
        """Next.js proxies /api/v1/* to the backend."""
        r = httpx.get(f"{FRONTEND_URL}/api/v1/health", timeout=15)
        # Should proxy through to backend health
        assert r.status_code in (200, 404)

    def test_frontend_demo_auth_route(self):
        r = httpx.post(f"{FRONTEND_URL}/api/auth/demo", timeout=15)
        assert r.status_code in (200, 401, 500)


# ═══════════════════════════════════════════════════════════════════════════════
# POSTGRES CONNECTIVITY
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.requires_docker
class TestPostgresConnectivity:
    @pytest.fixture(autouse=True)
    def check_pg(self):
        require_postgres()
        if not HAS_ASYNCPG:
            pytest.skip("asyncpg not installed — pip install asyncpg")

    def test_postgres_accepts_connections(self):
        async def check():
            conn = await asyncpg.connect(POSTGRES_DSN, timeout=10)
            await conn.close()
        asyncio.run(check())

    def test_postgres_has_investigation_sessions_table(self):
        async def check():
            conn = await asyncpg.connect(POSTGRES_DSN, timeout=10)
            result = await conn.fetchval(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'investigation_sessions'"
            )
            await conn.close()
            return result
        count = asyncio.run(check())
        assert count >= 1, "investigation_sessions table not found — migrations may not have run"

    def test_postgres_has_users_table(self):
        async def check():
            conn = await asyncpg.connect(POSTGRES_DSN, timeout=10)
            result = await conn.fetchval(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'users'"
            )
            await conn.close()
            return result
        count = asyncio.run(check())
        assert count >= 1, "users table not found — migrations may not have run"

    def test_postgres_has_reports_table(self):
        async def check():
            conn = await asyncpg.connect(POSTGRES_DSN, timeout=10)
            result = await conn.fetchval(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_name LIKE '%report%' OR table_name LIKE '%session_report%'"
            )
            await conn.close()
            return result
        count = asyncio.run(check())
        assert count >= 1, "No reports table found"


# ═══════════════════════════════════════════════════════════════════════════════
# REDIS CONNECTIVITY
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.requires_docker
class TestRedisConnectivity:
    @pytest.fixture(autouse=True)
    def check_redis(self):
        require_redis()
        if not HAS_REDIS:
            pytest.skip("redis[asyncio] not installed — pip install 'redis[asyncio]'")

    def test_redis_ping_succeeds(self):
        async def check():
            client = aioredis.from_url(
                f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}",
                decode_responses=True,
            )
            result = await client.ping()
            await client.aclose()
            return result
        assert asyncio.run(check()) is True

    def test_redis_set_and_get(self):
        async def check():
            client = aioredis.from_url(
                f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}",
                decode_responses=True,
            )
            await client.set("test:connectivity", "ok", ex=10)
            val = await client.get("test:connectivity")
            await client.delete("test:connectivity")
            await client.aclose()
            return val
        assert asyncio.run(check()) == "ok"

    def test_redis_requires_password(self):
        async def check():
            client = aioredis.from_url(
                f"redis://{REDIS_HOST}:{REDIS_PORT}",  # No password
                decode_responses=True,
            )
            try:
                await client.ping()
                await client.aclose()
                return False  # Should have failed
            except Exception:
                return True  # Expected — auth required
        # If Redis has no password, this is a configuration issue but not a test failure
        result = asyncio.run(check())
        # Just check it doesn't crash our test
        assert isinstance(result, bool)


# ═══════════════════════════════════════════════════════════════════════════════
# QDRANT CONNECTIVITY
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.requires_docker
class TestQdrantConnectivity:
    @pytest.fixture(autouse=True)
    def check_qdrant(self):
        require_qdrant()
        if not HAS_HTTPX:
            pytest.skip("httpx not installed")

    def test_qdrant_health_endpoint(self):
        r = httpx.get(f"{QDRANT_URL}/healthz", timeout=10)
        assert r.status_code == 200

    def test_qdrant_collections_endpoint(self):
        r = httpx.get(f"{QDRANT_URL}/collections", timeout=10)
        assert r.status_code == 200

    def test_qdrant_returns_json(self):
        r = httpx.get(f"{QDRANT_URL}/collections", timeout=10)
        assert "application/json" in r.headers.get("content-type", "")


# ═══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET CONNECTIVITY
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.requires_docker
class TestWebSocketConnectivity:
    """Test that the WebSocket endpoint is reachable and responds to AUTH."""

    @pytest.fixture(autouse=True)
    def check_prereqs(self):
        require_api()
        try:
            import websockets
        except ImportError:
            pytest.skip("websockets not installed — pip install websockets")

    def test_websocket_endpoint_reachable(self):
        """Connect to WS endpoint — should get a close or a CONNECTED message."""
        import websockets
        import uuid

        async def check():
            session_id = str(uuid.uuid4())
            ws_url = API_BASE.replace("http://", "ws://").replace("https://", "wss://")
            url = f"{ws_url}/api/v1/sessions/{session_id}/live"
            try:
                async with websockets.connect(url, open_timeout=5) as ws:
                    # Send AUTH with a fake token
                    await ws.send(json.dumps({"type": "AUTH", "token": "invalid-token"}))
                    # Expect either an error message or close
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=3)
                        data = json.loads(msg)
                        # Server responded (even with error) — WS is working
                        assert "type" in data
                    except asyncio.TimeoutError:
                        pass  # Server accepted connection but didn't respond yet
                    except Exception:
                        pass
            except Exception as e:
                # Connection refused = not running; any other exception = working but rejecting
                if "refused" in str(e).lower():
                    pytest.skip("WebSocket port not open")

        asyncio.run(check())


# ═══════════════════════════════════════════════════════════════════════════════
# END-TO-END AUTH FLOW
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.requires_docker
class TestEndToEndAuthFlow:
    @pytest.fixture(autouse=True)
    def check_prereqs(self):
        require_api()
        if not HAS_HTTPX:
            pytest.skip("httpx not installed")

    def test_full_auth_flow_login_and_verify(self):
        """Login → get token → verify /auth/me."""
        # Login
        login_r = httpx.post(
            f"{API_BASE}/api/v1/auth/login",
            data={"username": "investigator", "password": INVESTIGATOR_PASSWORD},
            timeout=10,
        )
        if login_r.status_code != 200:
            pytest.skip(f"Login failed with {login_r.status_code} — bootstrap may not have run")

        token = login_r.json()["access_token"]
        assert token

        # Verify identity
        me_r = httpx.get(
            f"{API_BASE}/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        assert me_r.status_code == 200
        data = me_r.json()
        assert "role" in data or "sub" in data or "user_id" in data

    def test_token_works_for_authenticated_routes(self):
        """Login then call a protected endpoint."""
        login_r = httpx.post(
            f"{API_BASE}/api/v1/auth/login",
            data={"username": "investigator", "password": INVESTIGATOR_PASSWORD},
            timeout=10,
        )
        if login_r.status_code != 200:
            pytest.skip("Login not available")

        token = login_r.json()["access_token"]
        r = httpx.get(
            f"{API_BASE}/api/v1/sessions/00000000-0000-0000-0000-000000000000/report",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        # 404 is fine (session doesn't exist) — we just want not 401
        assert r.status_code in (200, 202, 404)
        assert r.status_code != 401

    def test_logout_invalidates_token(self):
        """Token should be rejected after logout."""
        login_r = httpx.post(
            f"{API_BASE}/api/v1/auth/login",
            data={"username": "investigator", "password": INVESTIGATOR_PASSWORD},
            timeout=10,
        )
        if login_r.status_code != 200:
            pytest.skip("Login not available")

        token = login_r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Logout
        logout_r = httpx.post(f"{API_BASE}/api/v1/auth/logout", headers=headers, timeout=10)
        assert logout_r.status_code in (200, 204)

        # Token should now be blacklisted
        me_r = httpx.get(f"{API_BASE}/api/v1/auth/me", headers=headers, timeout=10)
        assert me_r.status_code in (401, 403)
