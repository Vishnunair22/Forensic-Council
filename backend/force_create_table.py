import asyncio
import sys
import os

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from infra.postgres_client import get_postgres_client

async def verify_and_create():
    with open("table_creation_log.txt", "w") as f:
        try:
            f.write("Connecting...\n")
            client = await get_postgres_client()
            f.write("Connected to DB.\n")
            
            f.write("Executing CREATE TABLE...\n")
            await client.execute("""
                CREATE TABLE IF NOT EXISTS evidence_artifacts (
                    artifact_id   UUID PRIMARY KEY,
                    parent_id     UUID REFERENCES evidence_artifacts(artifact_id),
                    root_id       UUID NOT NULL,
                    artifact_type VARCHAR(64) NOT NULL,
                    file_path     TEXT NOT NULL,
                    content_hash  VARCHAR(64) NOT NULL,
                    action        TEXT NOT NULL,
                    agent_id      VARCHAR(64) NOT NULL,
                    session_id    UUID NOT NULL,
                    timestamp_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    metadata      JSONB NOT NULL DEFAULT '{}'
                );
            """)
            f.write("Executed CREATE TABLE for evidence_artifacts\n")
            
            f.write("Adding indexes...\n")
            await client.execute("CREATE INDEX IF NOT EXISTS idx_ev_root ON evidence_artifacts(root_id);")
            await client.execute("CREATE INDEX IF NOT EXISTS idx_ev_session ON evidence_artifacts(session_id);")
            await client.execute("CREATE INDEX IF NOT EXISTS idx_ev_parent ON evidence_artifacts(parent_id);")
            await client.execute("CREATE INDEX IF NOT EXISTS idx_ev_type ON evidence_artifacts(artifact_type);")
            
            f.write("Checking tables...\n")
            tables = await client.fetch("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'evidence_artifacts'
            """)
            
            if tables:
                f.write(f"Vefified: Table '{tables[0]['table_name']}' exists!\n")
            else:
                f.write("FAILED: Table was not found after creation.\n")
                
            await client.disconnect()
        except Exception as e:
            f.write(f"Exception: {str(e)}\n")

if __name__ == "__main__":
    asyncio.run(verify_and_create())
