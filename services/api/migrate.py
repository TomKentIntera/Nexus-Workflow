#!/usr/bin/env python
"""
Database migration script.
Creates all tables defined in the models.
"""

import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import Base, engine
from app.models import Run, RunImage, RunImageApproval  # noqa: F401

def run_migrations():
    """Create all database tables."""
    print("Creating database tables...")
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables created successfully!")
        print("\nCreated tables:")
        for table in Base.metadata.tables:
            print(f"  - {table}")
    except Exception as e:
        print(f"❌ Error creating tables: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    run_migrations()

