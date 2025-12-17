#!/usr/bin/env python
"""
Migration script to add POSTED status to run_image_status enum.
Run this after updating the models to add the POSTED status.
"""

import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import engine
from sqlalchemy import text

def run_migration():
    """Add POSTED to the run_image_status enum."""
    print("Adding POSTED status to run_image_status enum...")
    try:
        with engine.begin() as conn:
            # Check if POSTED already exists
            result = conn.execute(text("""
                SELECT COLUMN_TYPE 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE() 
                AND TABLE_NAME = 'run_images' 
                AND COLUMN_NAME = 'status'
            """))
            row = result.fetchone()
            if row and 'posted' in row[0].lower():
                print("✅ POSTED status already exists in enum")
                return
            
            # Add POSTED to the enum
            # Note: MySQL ENUMs are case-sensitive for storage, so we need to match existing case
            # If existing values are uppercase, use uppercase; if lowercase, use lowercase
            # Check the existing enum values first
            existing_enum = row[0] if row else ""
            if 'GENERATED' in existing_enum or 'APPROVED' in existing_enum:
                # Use uppercase to match existing
                conn.execute(text("""
                    ALTER TABLE run_images 
                    MODIFY COLUMN status ENUM('GENERATED', 'APPROVED', 'REJECTED', 'POSTED') 
                    NOT NULL DEFAULT 'GENERATED'
                """))
            else:
                # Use lowercase
                conn.execute(text("""
                    ALTER TABLE run_images 
                    MODIFY COLUMN status ENUM('generated', 'approved', 'rejected', 'posted') 
                    NOT NULL DEFAULT 'generated'
                """))
            print("✅ Successfully added POSTED status to run_image_status enum")
    except Exception as e:
        print(f"❌ Error adding POSTED status: {str(e)}")
        print("Note: If the enum already contains 'posted', this is expected.")
        sys.exit(1)


if __name__ == "__main__":
    run_migration()

