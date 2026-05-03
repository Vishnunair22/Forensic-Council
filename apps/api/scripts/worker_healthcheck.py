#!/usr/bin/env python3
"""Worker healthcheck — verifies Redis connectivity and recent heartbeat."""
import os
import sys

import redis


def main() -> int:
    host = os.environ.get("REDIS_HOST", "redis")
    port = int(os.environ.get("REDIS_PORT", "6379"))
    password = os.environ.get("REDIS_PASSWORD", "")
    key = "forensic:worker:heartbeat"
    timeout = 3

    try:
        r = redis.Redis(
            host=host,
            port=port,
            password=password or None,
            socket_connect_timeout=timeout,
            socket_timeout=timeout,
            decode_responses=True,
        )
        if not r.exists(key):
            print(f"Worker heartbeat missing ({key})", file=sys.stderr)
            return 1
        print(f"Worker heartbeat present: {key}")
        return 0
    except redis.RedisError as e:
        print(f"Redis connectivity failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())