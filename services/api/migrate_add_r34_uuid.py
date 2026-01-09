#!/usr/bin/env python
"""
Migration script to add r34_uuid column to run_images table.
"""

import os
import sys

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from app.database import engine  # noqa: E402


def run_migration() -> None:
    print("Adding r34_uuid column to run_images table...")
    try:
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'run_images'
                      AND COLUMN_NAME = 'r34_uuid'
                    """
                )
            )
            exists = int(result.scalar_one() or 0) > 0
            if exists:
                print("✅ r34_uuid column already exists")
                return

            conn.execute(
                text(
                    """
                    ALTER TABLE run_images
                    ADD COLUMN r34_uuid VARCHAR(128) NULL
                    """
                )
            )
            print("✅ Successfully added r34_uuid column")
    except Exception as e:
        print(f"❌ Error adding r34_uuid column: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    run_migration()

