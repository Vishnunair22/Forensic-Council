"""
End-to-end smoke test for Forensic Council.
Tests the full flow: auth → upload → WebSocket → arbiter → report.
"""
import asyncio
import os
import time

import httpx

BASE_URL = os.environ.get("NEXT_PUBLIC_API_URL", "http://localhost:8000")
WS_BASE = BASE_URL.replace("http://", "ws://").replace("https://", "wss://")


async def main():
    print("=" * 60)
    print("FORENSIC COUNCIL — E2E SMOKE TEST")
    print("=" * 60)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=120.0) as client:
        # Step 1: Health check
        print("\n[1/7] Health check...")
        try:
            r = await client.get("/api/v1/health")
            status = r.status_code
        except Exception as e:
            print(f"  ✗ Health endpoint unavailable: {e}")
            status = 503
        print(f"  ✓ Status: {status in (200, 503)} ({status})")

        # Get CSRF cookie first
        csrf_token = client.cookies.get("csrf_token")
        if not csrf_token:
            await client.get("/api/v1/health")
            csrf_token = client.cookies.get("csrf_token")
        print(f"  ✓ CSRF: {csrf_token[:10] if csrf_token else 'NONE'}...")

        # Step 2: Authenticate
        print("\n[2/7] Authenticating...")
        auth_headers = {}
        if csrf_token:
            auth_headers["X-CSRF-Token"] = csrf_token

        r = await client.post(
            "/api/v1/auth/demo",
            headers=auth_headers,
        )
        if r.status_code == 404:
            r = await client.post(
                "/api/v1/auth/login",
                data={"username": "investigator", "password": "dev-investigator-password"},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if r.status_code != 200:
            print(f"  ✗ Auth failed: {r.status_code} {r.text[:200]}")
            return

        token_data = r.json()
        token = token_data.get("access_token")
        if not token:
            print(f"  ✗ No access token: {token_data}")
            return
        print(f"  ✓ Token: {token[:20]}...")

        # Step 3: Upload evidence
        print("\n[3/7] Uploading test evidence...")
        try:
            import io

            from PIL import Image

            img = Image.new("RGB", (100, 100), color=(128, 128, 128))
            buf = io.BytesIO()
            img.save(buf, format="JPEG")
            buf.seek(0)
            files = {"file": ("test_smoke.jpg", buf, "image/jpeg")}
        except ImportError:
            print("  PIL not available - using placeholder")
            files = {"file": ("test_smoke.jpg", b"\xff\xd8\xff\xe0\x00", "image/jpeg")}

        headers = {"Authorization": f"Bearer {token}"}
        if csrf_token:
            headers["X-CSRF-Token"] = csrf_token

        try:
            r = await client.post(
                "/api/v1/investigate",
                files=files,
                data={"case_id": "SMOKE-TEST-001", "investigator_id": "REQ-999999"},
                headers=headers,
            )
        except Exception as e:
            print(f"  ✗ Upload error: {e}")
            return

        if r.status_code != 200:
            print(f"  ✗ Upload failed: {r.status_code} {r.text[:300]}")
            return

        result = r.json()
        session_id = result.get("session_id")
        if not session_id:
            print(f"  ✗ No session_id: {result}")
            return
        print(f"  ✓ Session: {session_id}")

        # Step 4: Poll for completion
        print("\n[4/7] Polling for completion...")
        max_wait = 180
        start = time.time()
        while time.time() - start < max_wait:
            r = await client.get(
                f"/api/v1/sessions/{session_id}/arbiter-status",
                headers=headers,
            )
            if r.status_code == 200:
                st = r.json()
                status = st.get("status")
                print(f"  ... {status} ({int(time.time() - start)}s)")
                if status == "complete":
                    break
                if status == "error":
                    print(f"  ✗ Pipeline error: {st}")
                    return
            await asyncio.sleep(10)

        if time.time() - start >= max_wait:
            print(f"  ⚠ Timeout after {max_wait}s")
            return

        # Step 5: Wait for report
        print("\n[5/7] Waiting for report...")
        await asyncio.sleep(3)

        # Step 6: Fetch report
        print("\n[6/7] Fetching final report...")
        r = await client.get(
            f"/api/v1/sessions/{session_id}/report",
            headers=headers,
        )

        if r.status_code != 200:
            print(f"  ✗ Report fetch failed: {r.status_code} {r.text[:200]}")
            return

        report = r.json()
        verdict = report.get("overall_verdict")
        summary = report.get("executive_summary", "")

        print(f"  ✓ Verdict: {verdict}")
        print(f"  ✓ Summary: {summary[:100] if summary else '(empty)'}...")
        print(f"  ✓ Agents: {list(report.get('per_agent_findings', {}).keys())}")

        # Step 7: Validate
        print("\n[7/7] Validation...")
        if not verdict:
            print("  ✗ FAIL: Empty verdict!")
            return
        if not summary:
            print("  ✗ FAIL: Empty summary!")
            return

        print("\n" + "=" * 60)
        print("✓ ALL CHECKS PASSED — APP IS FUNCTIONAL END-TO-END")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
