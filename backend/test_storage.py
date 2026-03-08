import asyncio
from typing import Optional
import uuid
import tempfile
import sys
import os

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from core.config import get_settings
from infra.storage import LocalStorageBackend

async def test():
    settings = get_settings()
    print("Settings storage path:", settings.evidence_storage_path)
    storage = LocalStorageBackend()
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
        tmp.write(b"test data")
        tmp_path = tmp.name
        
    print("Temp path:", tmp_path)
    try:
        dest = await storage.store(
            root_id=uuid.uuid4(), 
            artifact_id=uuid.uuid4(), 
            data=b"test data", 
            extension=".png"
        )
        print("Success:", dest)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(test())
