#!/usr/bin/env python3
"""Hash a password using bcrypt. Usage: python hash_password.py <password>"""

import os
import sys

sys.path.insert(
    0,
    os.environ.get("APP_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)

# Apply bcrypt compatibility shim before passlib
from core._bcrypt_shim import ensure_bcrypt_compat
ensure_bcrypt_compat()

from passlib.context import CryptContext

if len(sys.argv) < 2:
    print("Usage: python hash_password.py <password>", file=sys.stderr)
    sys.exit(1)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
hashed = pwd_context.hash(sys.argv[1])
print(hashed)
