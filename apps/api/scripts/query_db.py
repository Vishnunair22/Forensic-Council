import asyncio
import json
import sys

from core.persistence.postgres_client import get_postgres_client

async def main():
    try:
        client = await get_postgres_client()
        
        print("=== Investigations ===")
        states = await client.fetch("SELECT session_id, case_id, status, created_at FROM investigation_state")
        for row in states:
            print(f"Session: {row['session_id']} | Case: {row['case_id']} | Status: {row['status']} | Created: {row['created_at']}")
        print()

        print("=== Failed/Incomplete Pipeline Traces ===")
        traces = await client.fetch(
            "SELECT session_id, agent_id, node_id, status, error, start_time, duration_ms FROM pipeline_traces WHERE status != 'COMPLETED'"
        )
        if not traces:
            print("No failed or incomplete traces found.")
        for row in traces:
            print(f"Session: {row['session_id']}")
            print(f"  Agent: {row['agent_id']} | Node: {row['node_id']} | Status: {row['status']} | Duration: {row['duration_ms']}ms")
            print(f"  Error: {row['error']}")
            print("-" * 50)
        print()
        
        print("=== Audit Logs (Errors/Warnings) ===")
        audit = await client.fetch(
            "SELECT session_id, action, status, details, timestamp_utc FROM audit_log WHERE status IN ('FAIL', 'FAILED', 'ERROR', 'WARN', 'WARNING')"
        )
        if not audit:
            print("No warning/error audit logs found.")
        for row in audit:
            print(f"Time: {row['timestamp_utc']} | Session: {row['session_id']} | Action: {row['action']} | Status: {row['status']}")
            print(f"  Details: {row['details']}")
            print("-" * 50)
        print()

    except Exception as e:
        print(f"Error querying database: {e}", file=sys.stderr)

if __name__ == '__main__':
    asyncio.run(main())
