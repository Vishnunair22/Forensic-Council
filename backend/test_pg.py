import asyncio
from typing import Optional
import uuid
import tempfile
import sys
import os
import datetime

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from core.config import get_settings
from infra.postgres_client import get_postgres_client

async def test():
    try:
        print("Starting test")
        settings = get_settings()
        print("Got settings")
        client = await get_postgres_client()
        print("Got postgres client")
        
        artifact_id = uuid.uuid4()
        root_id = artifact_id
        
        query = """
            INSERT INTO evidence_artifacts (
                artifact_id, parent_id, root_id, artifact_type,
                file_path, content_hash, action, agent_id,
                session_id, timestamp_utc, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        """
        
        await client.execute(
            query,
            artifact_id,
            None,
            root_id,
            "ORIGINAL",
            "/tmp/test.png",
            "fake_hash",
            "session_start",
            "Arbiter",
            uuid.uuid4(),
            datetime.datetime.now(datetime.timezone.utc),
            {"test": "val"},
        )
        print("Success inserting into evidence_artifacts")
        await client.disconnect()
    except Exception as e:
        import traceback
        traceback.print_exc(file=sys.stdout)
        print("Error:", repr(e))

if __name__ == "__main__":
    asyncio.run(test())
