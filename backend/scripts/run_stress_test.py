import asyncio
import os
import sys
import logging
from pathlib import Path
from uuid import uuid4

# Setup environment and paths
os.environ["APP_ENV"] = "testing"
sys.path.insert(0, "/app")

from orchestration.pipeline import ForensicCouncilPipeline

# Configure logging to be less noisy during the sweep
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger("stress_test")


async def run_stress_test():
    print("#" * 60)
    print(" FORENSIC COUNCIL SYSTEM INTEGRITY AUDIT (5-IMAGE STRESS TEST)")
    print("#" * 60 + "\n")

    pipeline = ForensicCouncilPipeline()
    stress_test_dir = Path("/app/storage/evidence/stress_test")
    test_images = sorted(list(stress_test_dir.glob("*")))

    if not test_images:
        print("Error: No test images found in /app/storage/evidence/stress_test")
        return

    for i, img_path in enumerate(test_images, 1):
        print(f"--- TEST CASE {i}/5: {img_path.name} ---")

        f"STRESS-TEST-{uuid4().hex[:8]}"
        investigator_id = "audit_agent"
        session_id = uuid4()

        try:
            # 1. Initialize components for this session
            await pipeline._initialize_components(session_id)

            # 2. Ingestion
            artifact = await pipeline.evidence_store.ingest(
                file_path=str(img_path),
                session_id=session_id,
                agent_id=investigator_id,
            )

            # 3. Initial Analysis Phase
            print("  [PHASE] Initial Analysis...")
            agent_results = await pipeline._run_agents_concurrent(
                evidence_artifact=artifact,
                session_id=session_id,
            )

            # Check Initial Results
            for res in agent_results:
                if res.error:
                    print(f"❌ {res.agent_id} CRASHED: {res.error}")
                else:
                    tools_run = [
                        f.get("metadata", {}).get("tool_name", "Unknown")
                        for f in res.findings
                    ]
                    print(f"✅ {res.agent_id} OK. Tools: {', '.join(tools_run)}")

            # 3. Deep Analysis Phase
            print("  [PHASE] Deep Analysis...")
            # We must simulate the deep analysis trigger

            # We run Agents 1, 3, 5 for deep pass on images
            for aid in ["Agent1", "Agent3", "Agent5"]:
                agent_class = pipeline.agent_factory._get_agent_class(aid)
                agent = agent_class(
                    agent_id=aid,
                    session_id=session_id,
                    evidence_artifact=artifact,
                    config=pipeline.config,
                    working_memory=pipeline.working_memory,
                    episodic_memory=pipeline.episodic_memory,
                    custody_logger=pipeline.custody_logger,
                    evidence_store=pipeline.evidence_store,
                )

                # Force deep mode
                if hasattr(agent, "analysis_phase"):
                    agent.analysis_phase = "deep"

                # Run deep investigation
                findings = await agent.run_deep_investigation()

                # Check for Gemini specific results
                gemini_found = any(
                    "gemini" in f.get("metadata", {}).get("tool_name", "").lower()
                    for f in [f.model_dump() for f in findings]
                )

                if gemini_found:
                    print(f"✨ {aid} Deep Pass: Gemini results verified.")
                else:
                    print(
                        f"⚠️ {aid} Deep Pass: No Gemini findings detected (using fallbacks)."
                    )

                # Audit finding content
                for f in findings:
                    f_dict = f.model_dump()
                    desc = f_dict.get("description", "")
                    tool = f_dict.get("metadata", {}).get("tool_name", "Unknown")

                    if "Gemini" in tool and (
                        not desc
                        or desc == "Visual analysis complete."
                        or "unidentified content" in desc
                    ):
                        if "test4_tiny" in img_path.name:
                            # Tiny images might legitimately have sparse descriptions
                            pass
                        else:
                            print(
                                f"🚨 ALERT: Empty/Sparse intelligence in {tool}: '{desc}'"
                            )

            print("-" * 40 + "\n")

        except Exception as e:
            print(f"❌ FATAL ERROR handling {img_path.name}: {e}")
            import traceback

            traceback.print_exc()

    print("#" * 60)
    print(" AUDIT COMPLETE")
    print("#" * 60)


if __name__ == "__main__":
    asyncio.run(run_stress_test())
