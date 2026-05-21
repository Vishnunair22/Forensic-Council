import asyncio
import os
import httpx
from pathlib import Path
from core.session_persistence import get_session_persistence

BASE_URL = os.environ.get("NEXT_PUBLIC_API_URL", "http://localhost:8000")
INVESTIGATOR_PASSWORD = os.environ.get("BOOTSTRAP_INVESTIGATOR_PASSWORD", "lliI0q6fKL3euObTKSyLV71lX7xJcxLN")

SESSIONS = {
    "JPEG": "7e97ad61-0be5-4207-8fa1-90e130fb60be",
    "PNG": "be537f21-ddb1-4308-aeee-efe21ded06ea",
    "WEBP": "df44d079-4751-4993-a230-992d711823b7"
}

async def fetch_details():
    persistence = await get_session_persistence()

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # Auth
        await client.get("/api/v1/health")
        csrf_token = client.cookies.get("csrf_token")
        headers = {"X-CSRF-Token": csrf_token} if csrf_token else {}
        
        r = await client.post(
            "/api/v1/auth/login",
            data={"username": "investigator", "password": INVESTIGATOR_PASSWORD},
            headers={"Content-Type": "application/x-www-form-urlencoded", **headers},
        )
        token = r.json().get("access_token")
        auth_headers = {"Authorization": f"Bearer {token}"}

        for fmt, sid in SESSIONS.items():
            print("\n" + "="*80)
            print(f"DETAILS FOR {fmt} SESSION: {sid}")
            print("="*80)
            
            # Fetch filename using raw SQL to bypass expiry filter
            filename = "Unknown"
            try:
                import uuid
                row = await persistence.client.fetch_one(
                    "SELECT pipeline_state, expires_at, NOW() as db_now FROM investigation_state WHERE session_id = $1",
                    uuid.UUID(sid)
                )
                if row:
                    print(f"DB Record Exists. Expires At: {row.get('expires_at')}, DB Now: {row.get('db_now')}")
                    p_state = row.get("pipeline_state")
                    print(f"Raw pipeline_state: {p_state}")
                    if p_state:
                        if isinstance(p_state, str):
                            import json
                            p_state = json.loads(p_state)
                        filename = p_state.get("original_filename", "Unknown")
                else:
                    print("DB Record does not exist in investigation_state!")
            except Exception as sql_err:
                print(f"SQL Error: {sql_err}")
            print(f"Original Filename: {filename}")
            
            # Fetch session metadata to get status message
            r = await client.get(f"/api/v1/sessions/{sid}/arbiter-status", headers=auth_headers)
            status_data = r.json()
            print(f"Status Message: {status_data.get('message')}")
            
            # Fetch report
            r = await client.get(f"/api/v1/sessions/{sid}/report", headers=auth_headers)
            if r.status_code != 200:
                print(f"Failed to fetch report: {r.status_code} {r.text}")
                continue
            
            report = r.json()
            print(f"Overall Verdict: {report.get('overall_verdict')}")
            print(f"Verdict Sentence: {report.get('verdict_sentence')}")
            print(f"Executive Summary:\n{report.get('executive_summary')}")
            print(f"Cryptographic Signature: {report.get('cryptographic_signature')}")
            print(f"Report Hash: {report.get('report_hash')}")
            
            print("\nPer-Agent Findings:")
            per_agent = report.get("per_agent_findings", {})
            for agent, findings in per_agent.items():
                print(f"  Agent: {agent}")
                for idx, f in enumerate(findings):
                    print(f"    Finding #{idx+1}:")
                    print(f"      Type: {f.get('finding_type')}")
                    print(f"      Verdict: {f.get('evidence_verdict')}")
                    print(f"      Confidence Raw: {f.get('confidence_raw')}")
                    print(f"      Reasoning Summary: {f.get('reasoning_summary')}")
                    print(f"      Court Statement: {f.get('court_statement')}")

if __name__ == "__main__":
    asyncio.run(fetch_details())
