#!/usr/bin/env python3
"""
Database Initialization Script
==============================

Delegates entirely to the versioned migration system to ensure the schema
is always in sync with what the application expects.

This script must NOT maintain its own SCHEMA_SQL — doing so causes drift
whenever a new migration is added.  All schema definitions live in
core/migrations.py.

Usage:
    python scripts/init_db.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import get_settings
from core.structured_logging import get_logger, configure_root_logger
from core.migrations import MigrationManager
from infra.postgres_client import PostgresClient

logger = get_logger(__name__)


async def init_database() -> bool:
    """
    Initialize the database schema via the versioned migration system.

    Runs all pending migrations (idempotent — safe to run multiple times).

    Returns:
        True if successful, False otherwise
    """
    configure_root_logger("INFO")

    settings = get_settings()
    logger.info(
        "Connecting to database...",
        host=settings.postgres_host,
        database=settings.postgres_db,
    )

    manager = MigrationManager()
    try:
        success = await manager.migrate()
        if not success:
            logger.error("Migration failed — schema may be incomplete")
            return False

        # Bootstrap users before calling status() — status() disconnects the
        # pool in its finally block (when _owned_client=True), so this must
        # happen while the connection is still open.
        await bootstrap_users(manager.client)

        status = await manager.status()
        logger.info(
            "Schema up to date",
            version=status["current_version"],
            applied=status["applied_count"],
        )

        logger.info("Database initialisation complete")
        return True

    except Exception as e:
        logger.error("Failed to initialise database", error=str(e))
        return False
    finally:
        await manager.disconnect()


async def bootstrap_users(client: PostgresClient) -> None:
    """
    Bootstrap admin and investigator users from environment variables.

    Environment Variables:
        BOOTSTRAP_ADMIN_USERNAME: Username for admin user (default: admin)
        BOOTSTRAP_ADMIN_PASSWORD: Password for admin user (required for admin creation)
        BOOTSTRAP_INVESTIGATOR_USERNAME: Username for investigator (default: investigator)
        BOOTSTRAP_INVESTIGATOR_PASSWORD: Password for investigator (required)
    """
    from passlib.context import CryptContext

    pwd_context = CryptContext(["bcrypt"], deprecated="auto")

    # Check if users table exists (migrations may not have run yet on first ever call)
    tables = await client.fetch(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'users'
        """
    )

    if not tables:
        logger.info("Users table not found — skipping bootstrap")
        return

    # Get admin credentials from environment
    admin_username = os.environ.get("BOOTSTRAP_ADMIN_USERNAME", "admin")
    admin_password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD")

    # Get investigator credentials from environment
    investigator_username = os.environ.get("BOOTSTRAP_INVESTIGATOR_USERNAME", "investigator")
    investigator_password = os.environ.get("BOOTSTRAP_INVESTIGATOR_PASSWORD")

    # Create admin user if password is provided
    if admin_password:
        admin_exists = await client.fetch_one(
            "SELECT 1 FROM users WHERE username = $1", admin_username
        )

        if not admin_exists:
            hashed = pwd_context.hash(admin_password)
            await client.execute(
                """
                INSERT INTO users
                    (user_id, username, hashed_password, role, is_active, is_disabled)
                VALUES ($1, $2, $3, 'admin', TRUE, FALSE)
                """,
                f"admin-{admin_username}",
                admin_username,
                hashed,
            )
            logger.info("Admin user created", username=admin_username)
        else:
            logger.info("Admin user already exists", username=admin_username)

    # Create investigator user if password is provided
    if investigator_password:
        investigator_exists = await client.fetch_one(
            "SELECT 1 FROM users WHERE username = $1", investigator_username
        )

        if not investigator_exists:
            hashed = pwd_context.hash(investigator_password)
            await client.execute(
                """
                INSERT INTO users
                    (user_id, username, hashed_password, role, is_active, is_disabled)
                VALUES ($1, $2, $3, 'investigator', TRUE, FALSE)
                """,
                f"inv-{investigator_username}",
                investigator_username,
                hashed,
            )
            logger.info("Investigator user created", username=investigator_username)
        else:
            logger.info("Investigator user already exists", username=investigator_username)


def main():
    """Main entry point."""
    success = asyncio.run(init_database())

    if success:
        print("\n[OK] Database initialisation complete — all migrations applied.")
        sys.exit(0)
    else:
        print("\n[ERROR] Database initialisation failed — check logs above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
