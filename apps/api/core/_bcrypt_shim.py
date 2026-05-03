"""
bcrypt compatibility shim.

bcrypt 4.x removed __about__; passlib 1.7.4 expects it.
This module provides a one-time shim that can be imported
by any entry point before passlib is loaded.

Usage:
    from core._bcrypt_shim import ensure_bcrypt_compat
    ensure_bcrypt_compat()
"""

import types


def ensure_bcrypt_compat() -> None:
    """
    Apply bcrypt compatibility shim if needed.

    Suppresses the "(trapped) error reading bcrypt version" warning at startup
    that occurs when bcrypt 4.x is used with passlib 1.7.4.
    """
    try:
        import bcrypt as _bcrypt  # type: ignore[attr-defined]

        if not hasattr(_bcrypt, "__about__"):
            _bcrypt.__about__ = types.SimpleNamespace(  # type: ignore[attr-defined]
                __version__=_bcrypt.__version__  # type: ignore[union-attr]
            )
    except ImportError:
        pass


if __name__ == "__main__":
    ensure_bcrypt_compat()
    print("bcrypt shim applied")
