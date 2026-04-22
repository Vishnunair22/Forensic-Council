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

from core.structured_logging import configure_root_logger, get_logger

# Configure logging immediately to ensure early errors are captured
configure_root_logger("INFO")

try:
    from core.config import get_settings
    from core.migrations import MigrationManager
    from core.persistence.postgres_client import PostgresClient
except Exception as e:
    print(f"\n[FATAL] Configuration error: {e}")
    sys.exit(1)

logger = get_logger(__name__)


async def init_database() -> bool:
    """
    Initialize the database schema via the versioned migration system.

    Runs all pending migrations (idempotent — safe to run multiple times).

    Returns:
        True if successful, False otherwise
    """
    settings = get_settings()
    max_retries = 10
    retry_delay = 3.0

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(
                f"Connecting to database (attempt {attempt}/{max_retries})...",
                host=settings.postgres_host,
                database=settings.postgres_db,
            )
            manager = MigrationManager()
            await manager.connect()

            success = await manager.migrate()
            if not success:
                logger.error("Migration failed — schema may be incomplete")
                await manager.disconnect()
                return False

            # Bootstrap users
            await bootstrap_users(manager.client)

            status = await manager.status()
            logger.info(
                "Schema up to date",
                version=status["current_version"],
                applied=status["applied_count"],
            )

            logger.info("Database initialization complete")
            await manager.disconnect()
            return True

        except Exception as e:
            if attempt < max_retries:
                logger.warning(f"Database connection attempt {attempt} failed: {e}. Retrying in {retry_delay}s...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error("Failed to initialize database after multiple attempts", error=str(e))
                return False
    return False


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
    investigator_username = os.environ.get(
        "BOOTSTRAP_INVESTIGATOR_USERNAME", "investigator"
    )
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
            hashed = pwd_context.hash(admin_password)
            await client.execute(
                """
                UPDATE users
                SET hashed_password = $2,
                    is_active = TRUE,
                    is_disabled = FALSE
                WHERE username = $1
                """,
                admin_username,
                hashed,
            )
            logger.info("Admin user password synchronized", username=admin_username)

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
            hashed = pwd_context.hash(investigator_password)
            await client.execute(
                """
                UPDATE users
                SET hashed_password = $2,
                    is_active = TRUE,
                    is_disabled = FALSE
                WHERE username = $1
                """,
                investigator_username,
                hashed,
            )
            logger.info(
                "Investigator user password synchronized", username=investigator_username
            )


def main():
    """Main entry point."""
    success = asyncio.run(init_database())

    if success:
        logger.info("Database migration job finished successfully — container will now exit")
        print("\n[OK] Database initialisation complete — all migrations applied.")
        sys.exit(0)
    else:
        logger.error("Database migration job failed")
        print("\n[ERROR] Database initialisation failed — check logs above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
