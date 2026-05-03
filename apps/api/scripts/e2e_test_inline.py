"""
End-to-end smoke test for Forensic Council.
"""
import asyncio
import httpx
from PIL import Image
import io


async def main():
    BASE_URL = "http://localhost:8000"

    print("=" * 60)
    print("FORENSIC COUNCIL — E2E SMOKE TEST")
    print("=" * 60)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=120.0, follow_redirects=True) as client:
        # Step 1: Health check
        print("\n[1/7] Health check...")
        r = await client.get("/api/v1/health")
        print(f"  Status: {r.status_code}")

        # Step 2: Get CSRF token
        print("\n[2/7] CSRF token...")
        csrf = client.cookies.get("csrf_token")
        if not csrf:
            await client.get("/api/v1/health")
            csrf = client.cookies.get("csrf_token")
        print(f"  CSRF: {csrf[:10] if csrf else None}...")

        # Step 3: Authenticate
        print("\n[3/7] Authenticating...")
        auth_headers = {}
        if csrf:
            auth_headers["X-CSRF-Token"] = csrf

        r = await client.post("/api/v1/auth/demo", headers=auth_headers)
        print(f"  Auth status: {r.status_code}")

        if r.status_code != 200:
            print(f"  Error: {r.text[:300]}")
            return

        token = r.json().get("access_token")
        if not token:
            print(f"  No token: {r.text}")
            return
        print(f"  Token: {token[:20]}...")

        # Step 4: Upload evidence
        print("\n[4/7] Uploading evidence...")
        headers = {"Authorization": f"Bearer {token}"}
        if csrf:
            headers["X-CSRF-Token"] = csrf

        img = Image.new("RGB", (100, 100), color=(128, 128, 128))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)
        files = {"file": ("test_smoke.jpg", buf, "image/jpeg")}

        r = await client.post(
            "/api/v1/investigate",
            files=files,
            data={"case_id": "SMOKE-TEST-001", "investigator_id": "REQ-999999"},
            headers=headers,
        )
        print(f"  Upload status: {r.status_code}")

        if r.status_code != 200:
            print(f"  Error: {r.text[:300]}")
            return

        session_id = r.json().get("session_id")
        if not session_id:
            print(f"  No session_id: {r.json()}")
            return
        print(f"  Session: {session_id}")

        # Step 5: Poll for completion
        print("\n[5/7] Polling for completion...")
        max_wait = 180
        start = asyncio.get_event_loop().time()
        while True:
            r = await client.get(
                f"/api/v1/sessions/{session_id}/arbiter-status",
                headers=headers,
            )
            if r.status_code == 200:
                st = r.json()
                status = st.get("status")
                elapsed = int(asyncio.get_event_loop().time() - start)
                print(f"  ... {status} ({elapsed}s)")
                if status == "complete":
                    break
                if status == "error":
                    print(f"  Pipeline error: {st}")
                    return
            await asyncio.sleep(10)
            if asyncio.get_event_loop().time() - start > max_wait:
                print(f"  Timeout after {max_wait}s")
                return

        # Step 6: Fetch report
        print("\n[6/7] Fetching report...")
        await asyncio.sleep(3)

        r = await client.get(f"/api/v1/sessions/{session_id}/report", headers=headers)
        print(f"  Report status: {r.status_code}")

        if r.status_code != 200:
            print(f"  Error: {r.text[:200]}")
            return

        report = r.json()
        verdict = report.get("overall_verdict")
        summary = report.get("executive_summary", "")

        print(f"  Verdict: {verdict}")
        print(f"  Summary: {summary[:100] if summary else '(empty)'}...")
        print(f"  Agents: {list(report.get('per_agent_findings', {}).keys())}")

        # Step 7: Validate
        print("\n[7/7] Validation...")
        if not verdict:
            print("  FAIL: Empty verdict!")
            return
        if not summary:
            print("  FAIL: Empty summary!")
            return

        print("\n" + "=" * 60)
        print("✓ ALL CHECKS PASSED")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())