#!/usr/bin/env python
"""
Migration script to create the migrations tracking table.
This table keeps track of which migrations have been applied.
"""

import os
import sys

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from app.database import engine  # noqa: E402


def run_migration() -> None:
    print("Creating migrations tracking table...")
    try:
        with engine.begin() as conn:
            # Check if table already exists
            result = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'schema_migrations'
                    """
                )
            )
            exists = int(result.scalar_one() or 0) > 0
            if exists:
                print("✅ schema_migrations table already exists")
                return

            conn.execute(
                text(
                    """
                    CREATE TABLE schema_migrations (
                        id VARCHAR(36) PRIMARY KEY,
                        migration_name VARCHAR(255) NOT NULL UNIQUE,
                        applied_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                        INDEX idx_migration_name (migration_name)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                )
            )
            print("✅ Successfully created schema_migrations table")
    except Exception as e:
        print(f"❌ Error creating schema_migrations table: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    run_migration()

