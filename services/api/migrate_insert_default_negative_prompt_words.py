#!/usr/bin/env python
"""
Migration script to insert default negative prompt words into the database.
"""

import os
import sys

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal  # noqa: E402
from app.models import NegativePromptWord  # noqa: E402
from sqlalchemy import select  # noqa: E402


def run_migration() -> None:
    print("Inserting default negative prompt words into database...")
    
    # Words from the current DEFAULT_NEGATIVE_PROMPT
    default_words = [
        "blurry",
        "low quality",
        "distorted",
        "watermark",
        "text",
        "speech bubble",
        "six fingers",
        "patreon logo"
    ]
    
    try:
        with SessionLocal() as session:
            # Get existing words
            existing_words = set(
                session.execute(
                    select(NegativePromptWord.word)
                ).scalars().all()
            )
            
            # Insert missing words
            inserted = []
            for word in default_words:
                if word not in existing_words:
                    session.add(NegativePromptWord(word=word))
                    inserted.append(word)
            
            if inserted:
                session.commit()
                print(f"✅ Successfully inserted {len(inserted)} words: {', '.join(inserted)}")
            else:
                print("✅ All default words already exist in database")
                
            # Show current count
            total = session.execute(select(NegativePromptWord)).scalars().all()
            print(f"   Total negative prompt words in database: {len(total)}")
            
    except Exception as e:
        print(f"❌ Error inserting negative prompt words: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_migration()

