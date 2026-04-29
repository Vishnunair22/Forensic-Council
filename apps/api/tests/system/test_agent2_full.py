import asyncio
import sys
from pathlib import Path
from uuid import uuid4

# Add apps/api to path
sys.path.append(str(Path(__file__).parent.parent))

from scripts.probe_initial_agent import _create_mp4, _create_wav

from agents.agent2_audio import Agent2Audio
from core.config import get_settings
from core.custody_logger import CustodyLogger
from core.episodic_memory import get_episodic_memory
from core.evidence import ArtifactType, EvidenceArtifact
from core.inter_agent_bus import InterAgentBus
from core.persistence.evidence_store import EvidenceStore
from core.working_memory import get_working_memory


async def test_agent2(sample_type: str):
    print(f"\n--- Testing Agent 2 with {sample_type.upper()} ---")

    # Create sample file
    tmp_dir = Path("/tmp/test_agent2")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    file_path = tmp_dir / f"test.{sample_type}"

    if sample_type == "wav":
        _create_wav(file_path)
        mime_type = "audio/wav"
    else:
        _create_mp4(file_path)
        mime_type = "video/mp4"

    session_id = uuid4()
    artifact = EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL,
        file_path=str(file_path),
        content_hash="mock_hash_audio",
        action="test",
        agent_id="test_runner",
        session_id=session_id,
        metadata={"mime_type": mime_type, "original_filename": file_path.name},
    )

    agent = Agent2Audio(
        agent_id="Agent2",
        session_id=session_id,
        evidence_artifact=artifact,
        config=get_settings(),
        working_memory=await get_working_memory(),
        episodic_memory=await get_episodic_memory(),
        custody_logger=CustodyLogger(),
        evidence_store=EvidenceStore(),
        inter_agent_bus=InterAgentBus(),
    )

    print("Running Initial Analysis...")
    initial_findings = await agent.run_investigation()
    print(f"Initial Findings: {len(initial_findings)}")
    for f in initial_findings:
        print(f"  - {f.finding_type}: {f.evidence_verdict} (Confidence: {f.confidence_raw})")

    print("\nRunning Deep Analysis...")
    deep_findings = await agent.run_deep_investigation()
    print(f"Deep Findings: {len(deep_findings)}")
    for f in deep_findings:
        print(f"  - {f.finding_type}: {f.evidence_verdict} (Confidence: {f.confidence_raw})")

    # Cleanup
    if file_path.exists():
        file_path.unlink()


async def main():
    await test_agent2("wav")
    await test_agent2("mp4")


if __name__ == "__main__":
    asyncio.run(main())
