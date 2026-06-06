#!/usr/bin/env python3
"""Worker healthcheck — verifies Redis connectivity and recent heartbeat."""
import os
import sys
import time

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
        value = r.get(key)
        if not value:
            print(f"Worker heartbeat missing ({key})", file=sys.stderr)
            return 1

        # Heartbeat must be fresh — a dead/hung worker leaves a stale key until TTL expires.
        # Threshold: 2× the heartbeat interval (workers write every ~30s by convention).
        _STALE_THRESHOLD_S = 120
        try:
            age = max(0.0, time.time() - float(value))
            if age > _STALE_THRESHOLD_S:
                print(
                    f"Worker heartbeat stale: {key}, age={age:.1f}s > {_STALE_THRESHOLD_S}s",
                    file=sys.stderr,
                )
                return 1
            print(f"Worker heartbeat present: {key}, age={age:.1f}s")
        except ValueError:
            print(f"Worker heartbeat present: {key}, value={value!r}")
        return 0
    except redis.RedisError as e:
        print(f"Redis connectivity failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
