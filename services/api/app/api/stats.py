from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_session
from ..models import Run, RunImage, RunImageStatus, RunStatus

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/images-per-hour")
def images_per_hour(
    hours: int = Query(default=24, ge=1, le=168, description="Number of hours to include (max 7 days)"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """
    Images generated per hour grouped by machine id.

    Returns buckets in UTC.
    """
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    # MySQL hour bucket
    hour_bucket = func.date_format(RunImage.created_at, "%Y-%m-%d %H:00:00")
    stmt = (
        select(
            hour_bucket.label("hour"),
            RunImage.generated_by_machine_id.label("machine_id"),
            func.count().label("count"),
        )
        .where(RunImage.created_at >= cutoff)
        .group_by(hour_bucket, RunImage.generated_by_machine_id)
        .order_by(hour_bucket.asc())
    )

    rows = session.execute(stmt).all()
    # normalize null machine_id
    data = [
        {"hour": r.hour, "machine_id": (r.machine_id or "unknown"), "count": int(r.count)}
        for r in rows
    ]
    machines = sorted({d["machine_id"] for d in data})
    hours_list = sorted({d["hour"] for d in data})
    return {"hours": hours_list, "machines": machines, "data": data}


@router.get("/reviewer-summary")
def reviewer_summary(session: Session = Depends(get_session)) -> dict[str, Any]:
    """
    Summary used by the reviewer UI homepage.

    - approved_images: images approved and awaiting posting
    - runs_need_review: runs with at least one GENERATED image (not yet approved/rejected/posted)
    - images_generated_last_hour: images created in the last 60 minutes
    - last_scheduled_post_time: the latest scheduled_time from approved/posted images
    """
    now = datetime.utcnow()
    cutoff = now - timedelta(hours=1)

    approved_images_stmt = (
        select(func.count())
        .select_from(RunImage)
        .where(RunImage.status == RunImageStatus.APPROVED)
    )
    approved_images = int(session.execute(approved_images_stmt).scalar_one() or 0)

    posted_images_stmt = (
        select(func.count())
        .select_from(RunImage)
        .where(RunImage.status == RunImageStatus.POSTED)
    )
    posted_images = int(session.execute(posted_images_stmt).scalar_one() or 0)

    runs_need_review_stmt = (
        select(func.count(func.distinct(RunImage.run_id)))
        .select_from(RunImage)
        .join(Run, Run.id == RunImage.run_id)
        .where(RunImage.status == RunImageStatus.GENERATED, Run.status != RunStatus.POSTED)
    )
    runs_need_review = int(session.execute(runs_need_review_stmt).scalar_one() or 0)

    images_last_hour_stmt = (
        select(func.count())
        .select_from(RunImage)
        .where(RunImage.created_at >= cutoff)
    )
    images_generated_last_hour = int(session.execute(images_last_hour_stmt).scalar_one() or 0)

    # Get the latest scheduled_time from approved or posted images
    last_scheduled_stmt = (
        select(func.max(RunImage.scheduled_time))
        .select_from(RunImage)
        .where(
            RunImage.scheduled_time.is_not(None),
            RunImage.status.in_([RunImageStatus.APPROVED, RunImageStatus.POSTED]),
        )
    )
    last_scheduled_post_time = session.execute(last_scheduled_stmt).scalar_one()

    result = {
        "approved_images": approved_images,
        "posted_images": posted_images,
        "runs_need_review": runs_need_review,
        "images_generated_last_hour": images_generated_last_hour,
    }
    
    if last_scheduled_post_time:
        result["last_scheduled_post_time"] = last_scheduled_post_time.isoformat()
        result["posts_scheduled_until"] = last_scheduled_post_time
    
    return result


@router.get("/images-last-hour-by-machine")
def images_last_hour_by_machine(session: Session = Depends(get_session)) -> dict[str, Any]:
    """
    Images generated in the last 60 minutes grouped by machine id.
    """
    cutoff = datetime.utcnow() - timedelta(hours=1)
    stmt = (
        select(
            RunImage.generated_by_machine_id.label("machine_id"),
            func.count().label("count"),
        )
        .where(RunImage.created_at >= cutoff)
        .group_by(RunImage.generated_by_machine_id)
        .order_by(func.count().desc())
    )
    rows = session.execute(stmt).all()
    data = [{"machine_id": (r.machine_id or "unknown"), "count": int(r.count)} for r in rows]
    total = sum(d["count"] for d in data)
    return {"data": data, "total": int(total)}

