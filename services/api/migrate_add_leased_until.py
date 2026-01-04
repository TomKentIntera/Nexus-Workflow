#!/usr/bin/env python
"""
Migration script to add leased_until column to runs table.
"""

import os
import sys

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from app.database import engine  # noqa: E402


def run_migration() -> None:
    print("Adding leased_until column to runs table...")
    try:
        with engine.begin() as conn:
            # Check if column already exists
            result = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'runs'
                      AND COLUMN_NAME = 'leased_until'
                    """
                )
            )
            exists = int(result.scalar_one() or 0) > 0
            if exists:
                print("✅ leased_until column already exists")
                return

            conn.execute(
                text(
                    """
                    ALTER TABLE runs
                    ADD COLUMN leased_until DATETIME(6) NULL
                    """
                )
            )
            print("✅ Successfully added leased_until column")
    except Exception as e:
        print(f"❌ Error adding leased_until column: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    run_migration()

