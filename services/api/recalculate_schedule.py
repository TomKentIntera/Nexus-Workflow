#!/usr/bin/env python
"""
Recalculate scheduled_time for approved images.

This script uses the same scheduling logic as the API to ensure consistency.
It applies random delays between WF_SCHEDULE_DELAY_MIN and WF_SCHEDULE_DELAY_MAX
between consecutive images, while respecting the posting window and max posts per day.
"""

import os
import sys
import random
from datetime import datetime, date, timedelta
from typing import Optional

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import RunImage, RunImageStatus
from app.config import get_settings


def _count_scheduled_for_day(session: Session, day: date, exclude_image_ids: Optional[set] = None) -> int:
    """Count how many images are scheduled for a given day.
    
    Args:
        session: Database session
        day: Date to check
        exclude_image_ids: Optional set of image IDs to exclude from count (e.g., images being rescheduled)
    """
    day_start = datetime.combine(day, datetime.min.time())
    day_end = datetime.combine(day, datetime.max.time())
    stmt = (
        select(func.count(RunImage.id))
        .where(
            RunImage.scheduled_time >= day_start,
            RunImage.scheduled_time <= day_end,
            RunImage.status.in_([RunImageStatus.APPROVED, RunImageStatus.POSTED]),
        )
    )
    if exclude_image_ids:
        stmt = stmt.where(~RunImage.id.in_(exclude_image_ids))
    return session.execute(stmt).scalar_one() or 0


def recalculate_schedule(dry_run: bool = False) -> None:
    """Recalculate scheduled_time for all approved images."""
    settings = get_settings()
    
    # Get configuration
    window_start_str = settings.posting_window_start
    window_end_str = settings.posting_window_end
    max_posts_per_day = settings.max_posts_per_day
    delay_min = settings.schedule_delay_min
    delay_max = settings.schedule_delay_max
    
    # Parse time strings using fromisoformat (same as API)
    try:
        window_start_time = datetime.fromisoformat(f"2000-01-01T{window_start_str}").time()
    except ValueError:
        raise ValueError(f"WF_POSTING_WINDOW_START must be HH:MM or HH:MM:SS (got '{window_start_str}').")
    
    try:
        window_end_time = datetime.fromisoformat(f"2000-01-01T{window_end_str}").time()
    except ValueError:
        raise ValueError(f"WF_POSTING_WINDOW_END must be HH:MM or HH:MM:SS (got '{window_end_str}').")
    
    if window_end_time <= window_start_time:
        raise ValueError("WF_POSTING_WINDOW_END must be later than WF_POSTING_WINDOW_START.")
    
    if max_posts_per_day <= 0:
        raise ValueError("WF_MAX_POSTS_PER_DAY must be > 0.")
    
    if delay_min < 0 or delay_max < 0:
        raise ValueError("Schedule delays must be >= 0 minutes.")
    if delay_min > delay_max:
        raise ValueError("WF_SCHEDULE_DELAY_MIN must be <= WF_SCHEDULE_DELAY_MAX.")
    
    session: Session = SessionLocal()
    try:
        # Get all approved images ordered by current scheduled_time
        stmt = (
            select(RunImage)
            .where(
                RunImage.status == RunImageStatus.APPROVED,
                RunImage.scheduled_time.is_not(None),
            )
            .order_by(RunImage.scheduled_time.asc(), RunImage.id.asc())
        )
        images = session.execute(stmt).scalars().all()
        
        if not images:
            print("No approved scheduled images found. Nothing to do.")
            return
        
        print(f"Found {len(images)} approved scheduled images.")
        print(f"Scheduling {max_posts_per_day}/day between {window_start_str}-{window_end_str}.")
        print(f"Using random delays between {delay_min}-{delay_max} minutes.")
        
        if dry_run:
            print("")
            print("🔍 DRY RUN MODE - No changes will be made to the database")
            print("")
        
        def _window_for(day: date) -> tuple[datetime, datetime]:
            return datetime.combine(day, window_start_time), datetime.combine(day, window_end_time)
        
        # When recalculating, start from today (or next available window)
        now = datetime.utcnow()
        today = now.date()
        window_start_dt, window_end_dt = _window_for(today)
        
        # Start from today's window start, or if we're past the window, start tomorrow
        if now < window_start_dt:
            base_time = window_start_dt
        elif now <= window_end_dt:
            # We're in the window, start from now
            base_time = now
        else:
            # We're past today's window, start tomorrow
            tomorrow = today + timedelta(days=1)
            window_start_dt, window_end_dt = _window_for(tomorrow)
            base_time = window_start_dt
        
        print(f"Starting schedule from: {base_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Schedule each image sequentially, applying random delays
        scheduled_times = []
        current_time = base_time
        
        # Track how many we've scheduled per day as we go
        scheduled_per_day = {}
        
        # Get set of image IDs we're rescheduling (to exclude from existing count)
        rescheduling_ids = {img.id for img in images}
        
        for idx, image in enumerate(images):
            if idx == 0:
                # First image starts at base_time (already set above)
                current_time = base_time
            else:
                # Apply random delay from previous image
                delay_minutes = delay_min if delay_min == delay_max else random.randint(delay_min, delay_max)
                current_time = current_time + timedelta(minutes=delay_minutes)
            
            day = current_time.date()
            window_start_dt, window_end_dt = _window_for(day)
            
            # Ensure we're within the window
            if current_time < window_start_dt:
                current_time = window_start_dt
            if current_time > window_end_dt:
                day = day + timedelta(days=1)
                window_start_dt, window_end_dt = _window_for(day)
                current_time = window_start_dt
            
            # Check if we've exceeded max posts per day
            # Exclude images we're rescheduling from the existing count
            day_key = day.isoformat()
            existing_count = _count_scheduled_for_day(session, day, exclude_image_ids=rescheduling_ids)
            our_count = scheduled_per_day.get(day_key, 0)
            
            while existing_count + our_count >= max_posts_per_day:
                day = day + timedelta(days=1)
                window_start_dt, window_end_dt = _window_for(day)
                current_time = window_start_dt
                day_key = day.isoformat()
                existing_count = _count_scheduled_for_day(session, day, exclude_image_ids=rescheduling_ids)
                our_count = scheduled_per_day.get(day_key, 0)
            
            # Update our count for this day
            scheduled_per_day[day_key] = our_count + 1
            
            scheduled_times.append((image.id, current_time))
        
        if dry_run:
            # Show preview
            print("Sample schedule preview:")
            print("  First 5 images:")
            for i, (img_id, scheduled_time) in enumerate(scheduled_times[:5], 1):
                print(f"    #{i}: {scheduled_time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            if len(scheduled_times) > 5:
                print("  ...")
                print("  Last 5 images:")
                for i, (img_id, scheduled_time) in enumerate(scheduled_times[-5:], len(scheduled_times) - 4):
                    print(f"    #{i}: {scheduled_time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            first_time = scheduled_times[0][1]
            final_time = scheduled_times[-1][1]
            # Calculate days based on actual scheduled dates, not database start_date
            days_required = (final_time.date() - first_time.date()).days + 1
            
            print("")
            print("Summary:")
            print(f"  - Total images: {len(images)}")
            print(f"  - Images per day: {max_posts_per_day}")
            print(f"  - Days required: {days_required}")
            print(f"  - First posting date: {first_time.date()}")
            print(f"  - First posting datetime: {first_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  - Final posting date: {final_time.date()}")
            print(f"  - Final posting datetime: {final_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print("")
            print("To apply these changes, run without --dry-run flag.")
        else:
            # Apply the schedule
            for image_id, scheduled_time in scheduled_times:
                image = session.get(RunImage, image_id)
                if image:
                    image.scheduled_time = scheduled_time
            
            session.commit()
            print("Recalculation complete.")
            
    finally:
        session.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv or "-n" in sys.argv
    try:
        recalculate_schedule(dry_run=dry_run)
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

