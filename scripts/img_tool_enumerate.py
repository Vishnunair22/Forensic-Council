"""Enumerate registered tools per image format per agent, and which gate as NOT_APPLICABLE."""
import asyncio, os, tempfile
from unittest.mock import AsyncMock
from uuid import uuid4
os.environ.setdefault("APP_ENV", "testing")
from skimage import data
from PIL import Image
from agents.agent1_image import Agent1Image
from agents.agent3_object import Agent3Object
from agents.agent5_metadata import Agent5Metadata
from core.config import get_settings
from core.evidence import ArtifactType, EvidenceArtifact
from core.file_type_policy import get_applicable_agents, content_aware_gate

AGENTS = {"Agent1": Agent1Image, "Agent3": Agent3Object, "Agent5": Agent5Metadata}

FORMATS = [
    ("JPEG", ".jpg", "image/jpeg", True),
    ("PNG", ".png", "image/png", False),
    ("TIFF", ".tiff", "image/tiff", False),
    ("WEBP", ".webp", "image/webp", False),
    ("GIF", ".gif", "image/gif", False),
    ("BMP", ".bmp", "image/bmp", False),
]


def make_image(fmt, suffix, with_exif):
    arr = data.astronaut()  # 512x512 RGB real photo (person)
    im = Image.fromarray(arr)
    p = tempfile.mktemp(suffix=suffix)
    kw = {}
    if fmt == "JPEG":
        kw["quality"] = 90
        if with_exif:
            ex = Image.Exif(); ex[271] = "Canon"; ex[272] = "EOS 5D"; kw["exif"] = ex
    if fmt == "GIF":
        im = im.convert("P")
    im.save(p, fmt, **kw)
    return p


def mk_agent(aid, path, mime):
    art = EvidenceArtifact.create_root(
        artifact_type=ArtifactType.ORIGINAL, file_path=path, content_hash="h",
        action="upload", agent_id="system", session_id=uuid4(), metadata={"mime_type": mime})
    return AGENTS[aid](agent_id=aid, session_id=uuid4(), evidence_artifact=art,
        config=get_settings(), working_memory=AsyncMock(), episodic_memory=AsyncMock(),
        custody_logger=AsyncMock(), evidence_store=AsyncMock())


async def main():
    for fmt, suffix, mime, lossy in FORMATS:
        p = make_image(fmt, suffix, lossy)
        print("\n" + "=" * 78)
        print(f"  {fmt}  ({mime})  applicable={get_applicable_agents(mime)}")
        print("=" * 78)
        for aid in get_applicable_agents(mime):
            if aid not in AGENTS:
                continue
            try:
                agent = mk_agent(aid, p, mime)
                reg = await agent.build_tool_registry()
                tools = sorted(reg._tools.keys())
            except Exception as e:
                print(f"  {aid}: registry build FAILED: {type(e).__name__}: {e}")
                continue
            runs, gated = [], []
            for t in tools:
                if content_aware_gate(t, p, mime):
                    gated.append(t)
                else:
                    runs.append(t)
            print(f"  {aid}: {len(runs)} run / {len(gated)} gated")
            print(f"    RUN:   {runs}")
            if gated:
                print(f"    GATED: {gated}")
        os.unlink(p)


asyncio.run(main())
