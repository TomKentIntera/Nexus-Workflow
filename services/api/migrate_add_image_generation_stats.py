#!/usr/bin/env python
"""
Migration script to add image_generation_stats table.
"""

import os
import sys

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from app.database import engine  # noqa: E402


def run_migration() -> None:
    print("Creating image_generation_stats table...")
    try:
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'image_generation_stats'
                    """
                )
            )
            exists = int(result.scalar_one() or 0) > 0
            if exists:
                print("✅ image_generation_stats table already exists")
                return

            conn.execute(
                text(
                    """
                    CREATE TABLE image_generation_stats (
                        id VARCHAR(36) PRIMARY KEY,
                        generated_at DATETIME NOT NULL,
                        machine_id VARCHAR(64) NULL
                    )
                    """
                )
            )
            print("✅ Successfully created image_generation_stats table")
    except Exception as e:
        print(f"❌ Error creating image_generation_stats table: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    run_migration()
