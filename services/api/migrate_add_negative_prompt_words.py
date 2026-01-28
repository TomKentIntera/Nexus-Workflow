#!/usr/bin/env python
"""
Migration script to create negative_prompt_words table.
"""

import os
import sys

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from app.database import engine  # noqa: E402


def run_migration() -> None:
    print("Creating negative_prompt_words table...")
    try:
        with engine.begin() as conn:
            # Check if table already exists
            result = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'negative_prompt_words'
                    """
                )
            )
            exists = int(result.scalar_one() or 0) > 0
            if exists:
                print("✅ negative_prompt_words table already exists")
                return

            conn.execute(
                text(
                    """
                    CREATE TABLE negative_prompt_words (
                        id VARCHAR(36) PRIMARY KEY,
                        word VARCHAR(255) NOT NULL UNIQUE,
                        created_at DATETIME(6) NOT NULL,
                        updated_at DATETIME(6) NOT NULL
                    )
                    """
                )
            )
            print("✅ Successfully created negative_prompt_words table")
    except Exception as e:
        print(f"❌ Error creating negative_prompt_words table: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    run_migration()

