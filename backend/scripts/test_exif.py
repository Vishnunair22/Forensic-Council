import asyncio
from core.evidence import EvidenceArtifact
from tools.metadata_tools import exif_extract

async def main():
    try:
        a = EvidenceArtifact(
            artifact_id='123',
            case_id='123',
            investigator_id='123',
            evidence_type='image',
            file_path='tests/test_images/test_image.jpg',
            original_filename='test.jpg'
        )
        res = await exif_extract(a)
        print("RESULT:", res)
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
