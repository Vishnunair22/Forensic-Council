#!/usr/bin/env python3
import sys
sys.path.insert(0, '/app')
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
hashed = pwd_context.hash('demo123')
print(hashed)
