from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_session
from ..models import RunImage

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

