from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..database import get_session
from ..models import Run, RunImage, RunImageStatus, RunStatus
from ..services.artist_scores import compute_artist_scores_from_runs

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
def reviewer_summary(session: Session = Depends(get_session)) -> dict[str, int]:
    """
    Summary used by the reviewer UI homepage.

    - approved_images: images approved and awaiting posting
    - runs_need_review: runs with at least one GENERATED image (not yet approved/rejected/posted)
    - images_generated_last_hour: images created in the last 60 minutes
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

    return {
        "approved_images": approved_images,
        "posted_images": posted_images,
        "runs_need_review": runs_need_review,
        "images_generated_last_hour": images_generated_last_hour,
    }


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


@router.get("/artist-scores")
def artist_scores(
    limit: int = Query(default=50, ge=1, le=500, description="Max artists to return"),
    min_posts: int = Query(default=1, ge=1, le=1000000, description="Minimum number of posts required"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """
    Rank artists based on run outcomes, normalized by number of posts with that artist tag.

    Normalization:
      score = (approvals - rejections) / posts

    Where:
    - approvals: number of APPROVED or POSTED images across runs containing that artist tag
    - rejections: number of REJECTED images across runs containing that artist tag
    - posts: number of runs containing that artist tag (case-insensitive)
    """
    pos_case = case((RunImage.status.in_([RunImageStatus.APPROVED, RunImageStatus.POSTED]), 1), else_=0)
    neg_case = case((RunImage.status == RunImageStatus.REJECTED, 1), else_=0)

    # One row per run: includes parameter_blob (for artist tags) plus outcome counts.
    stmt = (
        select(
            Run.parameter_blob,
            func.coalesce(func.sum(pos_case), 0).label("approvals"),
            func.coalesce(func.sum(neg_case), 0).label("rejections"),
        )
        .select_from(Run)
        .join(RunImage, RunImage.run_id == Run.id, isouter=True)
        # Ignore deleted/posted runs at the run level only for workflow UI; for scoring we
        # still want them included. So we intentionally do NOT filter by Run.status here.
        .group_by(Run.id)
    )

    rows = session.execute(stmt).all()
    # compute_artist_scores_from_runs expects (parameter_blob, approvals, rejections)
    scored = compute_artist_scores_from_runs(((r.parameter_blob, int(r.approvals), int(r.rejections)) for r in rows))
    filtered = [r for r in scored if r.posts >= min_posts]
    filtered = filtered[:limit]

    return {
        "data": [
            {
                "artist": r.artist,
                "score": r.score,
                "posts": r.posts,
                "approvals": r.approvals,
                "rejections": r.rejections,
                "delta": r.delta,
            }
            for r in filtered
        ],
        "limit": limit,
        "min_posts": min_posts,
    }

