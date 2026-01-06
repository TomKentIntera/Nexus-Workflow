#!/usr/bin/env python
"""
Migration script to add fanvue_uuid column to run_images table.
"""

import os
import sys

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from app.database import engine  # noqa: E402


def run_migration() -> None:
    print("Adding fanvue_uuid column to run_images table...")
    try:
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'run_images'
                      AND COLUMN_NAME = 'fanvue_uuid'
                    """
                )
            )
            exists = int(result.scalar_one() or 0) > 0
            if exists:
                print("✅ fanvue_uuid column already exists")
                return

            conn.execute(
                text(
                    """
                    ALTER TABLE run_images
                    ADD COLUMN fanvue_uuid VARCHAR(128) NULL
                    """
                )
            )
            print("✅ Successfully added fanvue_uuid column")
    except Exception as e:
        print(f"❌ Error adding fanvue_uuid column: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    run_migration()

