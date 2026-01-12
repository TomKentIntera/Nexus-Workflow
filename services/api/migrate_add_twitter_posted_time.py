#!/usr/bin/env python
"""
Migration script to add twitter_posted_time column to run_images table.
"""

import os
import sys

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from app.database import engine  # noqa: E402


def run_migration() -> None:
    print("Adding twitter_posted_time column to run_images table...")
    try:
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'run_images'
                      AND COLUMN_NAME = 'twitter_posted_time'
                    """
                )
            )
            exists = int(result.scalar_one() or 0) > 0
            if exists:
                print("✅ twitter_posted_time column already exists")
                return

            conn.execute(
                text(
                    """
                    ALTER TABLE run_images
                    ADD COLUMN twitter_posted_time DATETIME NULL
                    """
                )
            )
            print("✅ Successfully added twitter_posted_time column")
    except Exception as e:
        print(f"❌ Error adding twitter_posted_time column: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    run_migration()

