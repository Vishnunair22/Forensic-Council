"""
Integration test conftest — ensures api.routes is importable.

The backend root (apps/api/) must NOT be a Python package itself,
otherwise pytest walks up the tree and adds apps/ to sys.path first,
which makes 'api' resolve to the backend root instead of apps/api/api/.
This conftest documents that invariant and provides a safe fallback.
"""
import os
import sys

# Guarantee the backend package root is on sys.path
_backend_root = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)
