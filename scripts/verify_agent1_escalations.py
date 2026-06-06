import asyncio, os, tempfile
from unittest.mock import AsyncMock
from uuid import uuid4
os.environ.setdefault("APP_ENV", "testing")
from PIL import Image, ImageDraw
from agents.agent1_image import Agent1Image
from core.config import get_settings
from core.evidence import ArtifactType, EvidenceArtifact
from core.task_router import get_task_router


def mk_jpeg():
    p = tempfile.mktemp(suffix=".jpg")
    im = Image.new("RGB", (256, 256), (180, 120, 90))
    d = ImageDraw.Draw(im); d.rectangle([40, 40, 200, 200], fill=(30, 60, 160))
    im.save(p, "JPEG", quality=90)
    return p


def mk_agent(path, mime):
    art = EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL, file_path=path, content_hash="h",
        action="upload", agent_id="system", session_id=uuid4(), metadata={"mime_type": mime})
    return Agent1Image(agent_id="Agent1", session_id=uuid4(), evidence_artifact=art,
        config=get_settings(), working_memory=AsyncMock(), episodic_memory=AsyncMock(),
        custody_logger=AsyncMock(), evidence_store=AsyncMock())


# The exact descriptions the reactive rules inject -> expected tool
INJECTIONS = {
    "Run roi_extract for localized forensic region analysis": "roi_extract",
    "Run adversarial_robustness_check for anti-forensics perturbation stability check": "adversarial_robustness_check",
    "Run jpeg_ghost_detect for double compression analysis": "jpeg_ghost_detect",
    "Run deepfake_frequency_check for GAN/Diffusion artifacts": "deepfake_frequency_check",
}


async def main():
    p = mk_jpeg()
    agent = mk_agent(p, "image/jpeg")
    reg = await agent.build_tool_registry()
    tools = sorted(reg._tools.keys())
    print("REGISTERED:", tools)
    need = ["roi_extract", "adversarial_robustness_check", "jpeg_ghost_detect", "deepfake_frequency_check"]
    for t in need:
        assert t in tools, f"MISSING {t}"
    print("\nAll 4 reactive tools registered OK\n")

    router = get_task_router()
    tool_list = reg.list_tools()

    def rname(desc):
        r = router.route(desc, tool_list, agent_id="Agent1")
        return getattr(r, "name", r)

    ok = True
    print("-- injected escalations --")
    for desc, expected in INJECTIONS.items():
        got = rname(desc)
        if got != expected:
            ok = False
        print(f"  {got:32} (want {expected:32}) {'OK' if got==expected else '<<< MISROUTE'}")

    # Regression: initial-plan task descriptions must still route to their own tool,
    # not get hijacked by the newly-registered follow-up tools.
    print("-- initial-plan tasks (regression) --")
    initial = {
        "Run neural_ela manipulation detection": "neural_ela",
        "Run frequency_domain_analysis for FFT anomaly analysis": "frequency_domain_analysis",
        "Run neural_fingerprint for SigLIP2 perceptual fingerprint": "neural_fingerprint",
    }
    for desc, expected in initial.items():
        got = rname(desc)
        if got != expected:
            ok = False
        print(f"  {got:32} (want {expected:32}) {'OK' if got==expected else '<<< MISROUTE'}")

    print("\nROUTER", "OK" if ok else "HAS MISROUTES")
    os.unlink(p)


asyncio.run(main())
