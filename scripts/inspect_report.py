import asyncio, os, httpx, json, sys

SID = sys.argv[1] if len(sys.argv) > 1 else "183c6928-12cd-48f9-926d-eff1705fd2af"


async def m():
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as c:
        r = await c.post("/api/v1/auth/login", data={"username": "investigator", "password": os.environ["BOOTSTRAP_INVESTIGATOR_PASSWORD"]})
        c.headers["Authorization"] = "Bearer " + r.json()["access_token"]
        rep = (await c.get(f"/api/v1/sessions/{SID}/report")).json()

    print("GLOBAL 'You are' leak:", "You are" in json.dumps(rep))

    def show(label, val, n=600):
        t = type(val).__name__
        s = json.dumps(val, indent=1) if isinstance(val, (dict, list)) else str(val)
        print(f"\n--- {label} ({t}) ---\n{s[:n]}")

    pa = rep.get("per_agent_analysis", {})
    show("per_agent_analysis type/keys", list(pa.keys()) if isinstance(pa, dict) else pa)
    if isinstance(pa, dict):
        for k, v in pa.items():
            show(f"per_agent_analysis[{k}]", v, 500)

    ps = rep.get("per_agent_summary", {})
    if isinstance(ps, dict):
        for k in ("Agent2", "Agent5"):
            show(f"per_agent_summary[{k}]", ps.get(k), 400)

    f2 = rep.get("per_agent_findings", {}).get("Agent2", [])
    print(f"\n--- Agent2 findings: {len(f2)} ---")
    for f in (f2 if isinstance(f2, list) else [])[:6]:
        if isinstance(f, dict):
            print(" -", f.get("finding_type"), "|", f.get("evidence_verdict"), "|", f.get("status"), "|", (f.get("reasoning_summary") or "")[:80])

    show("per_agent_metrics[Agent2]", rep.get("per_agent_metrics", {}).get("Agent2"), 400)
    show("degraded_findings_summary", rep.get("degraded_findings_summary"), 400)


asyncio.run(m())
