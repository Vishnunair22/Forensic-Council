import asyncio
import uuid
import sys
import os
import datetime
import traceback

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from core.config import get_settings
from infra.postgres_client import get_postgres_client

async def test():
    with open("db_diag.txt", "w") as f:
        try:
            f.write("Starting DB Test...\n")
            settings = get_settings()
            f.write(f"Settings DB Host: {settings.postgres_host}\n")
            client = await get_postgres_client()
            f.write("Connected to DB successfully.\n")
            
            artifact_id = uuid.uuid4()
            query = """
                INSERT INTO evidence_artifacts (
                    artifact_id, parent_id, root_id, artifact_type,
                    file_path, content_hash, action, agent_id,
                    session_id, timestamp_utc, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """
            
            f.write("Executing INSERT...\n")
            await client.execute(
                query,
                artifact_id,
                None,
                artifact_id,
                "ORIGINAL",
                "/tmp/test.png",
                "fake_hash",
                "session_start",
                "Arbiter",
                uuid.uuid4(),
                datetime.datetime.now(datetime.timezone.utc),
                {"test": "val"},
            )
            f.write("Success inserting into evidence_artifacts\n")
            await client.disconnect()
        except Exception as e:
            f.write("--- EXCEPTION CAUGHT ---\n")
            f.write(traceback.format_exc())
            f.write(f"\nException Message: {str(e)}\n")

if __name__ == "__main__":
    asyncio.run(test())
