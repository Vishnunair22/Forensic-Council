import asyncio
import uuid
import sys
import os
from datetime import datetime

# Add apps/api to path
sys.path.append("/app/apps/api")

from agents.agent3_object import Agent3Object
from core.evidence import EvidenceArtifact, ArtifactType
from core.config import get_settings
from core.working_memory import WorkingMemory
from core.episodic_memory import EpisodicMemory
from core.custody_logger import get_custody_logger
from core.persistence.evidence_store import EvidenceStore

async def test_agent3_full():
    settings = get_settings()
    session_id = uuid.uuid4()
    
    # Path to sample image
    sample_path = "/app/tests/fixtures/alley_object_test.png"
    
    if not os.path.exists(sample_path):
        print(f"ERROR: Sample path {sample_path} does not exist.")
        return

    # 1. Create Evidence Artifact
    artifact = EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=sample_path,
        content_hash="dummy_hash",
        action="test_ingestion",
        agent_id="test_runner",
        session_id=session_id,
        metadata={"mime_type": "image/png"}
    )

    # 2. Setup Infrastructure
    working_memory = WorkingMemory()
    episodic_memory = EpisodicMemory()
    custody_logger = await get_custody_logger()
    evidence_store = EvidenceStore(settings)

    # 3. Initialize Agent
    agent = Agent3Object(
        agent_id="Agent3_Test",
        session_id=session_id,
        evidence_artifact=artifact,
        config=settings,
        working_memory=working_memory,
        episodic_memory=episodic_memory,
        custody_logger=custody_logger,
        evidence_store=evidence_store
    )

    print(f"\n=== Starting Agent 3 Initial Pass (Session: {session_id}) ===")
    initial_findings = await agent.run_investigation()
    
    print(f"\nInitial Findings: {len(initial_findings)}")
    for f_obj in initial_findings:
        f = f_obj.model_dump()
        meta = f.get("metadata", {})
        print(f"  - {f.get('finding_type')}: {f.get('evidence_verdict')} (Confidence: {f.get('confidence_score')})")
        if 'tool_name' in meta:
             print(f"    Tool: {meta['tool_name']}")

    print(f"\n=== Starting Agent 3 Deep Pass ===")
    deep_findings = await agent.run_deep_investigation()
    
    print(f"\nDeep Findings: {len(deep_findings)}")
    for f_obj in deep_findings:
        f = f_obj.model_dump()
        meta = f.get("metadata", {})
        print(f"  - {f.get('finding_type')}: {f.get('evidence_verdict')} (Confidence: {f.get('confidence_score')})")
        if 'tool_name' in meta:
             print(f"    Tool: {meta['tool_name']}")

if __name__ == "__main__":
    asyncio.run(test_agent3_full())
