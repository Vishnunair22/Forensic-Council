import asyncio, tempfile, random
from uuid import uuid4
from skimage import data
from PIL import Image
from core.evidence import ArtifactType, EvidenceArtifact


async def m():
    from core.vision_local_ensemble import analyze_local_visual_profile
    out = []
    for tag, pert, fmt, suf in (
        ("BMP-clean", False, "BMP", ".bmp"),
        ("BMP-randpix", True, "BMP", ".bmp"),
        ("JPEG-clean", False, "JPEG", ".jpg"),
        ("PNG-clean", False, "PNG", ".png"),
    ):
        p = tempfile.mktemp(suffix=suf)
        im = Image.fromarray(data.astronaut())
        if pert:
            im.putpixel((0, 0), (random.randint(0, 255),) * 3)
        im.save(p, fmt)
        art = EvidenceArtifact.create_root(artifact_type=ArtifactType.ORIGINAL, file_path=p, content_hash="h",
            action="upload", agent_id="s", session_id=uuid4(), metadata={"mime_type": f"image/{suf[1:]}"})
        r = await analyze_local_visual_profile(art)
        out.append(f"{tag:14} verdict={getattr(r,'_authenticity_verdict',None):12} signals={r.manipulation_signals}")
    with open("/tmp/bmp_test.txt", "w") as f:
        f.write("\n".join(out) + "\n")


asyncio.run(m())
