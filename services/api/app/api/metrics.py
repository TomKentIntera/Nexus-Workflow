from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_session
from ..models import Run, RunImage, RunImageStatus, RunStatus

router = APIRouter(tags=["metrics"])


def _escape_label_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _format_metric(name: str, value: int, labels: dict[str, str] | None = None) -> str:
    if labels:
        label_pairs = [f'{key}="{_escape_label_value(val)}"' for key, val in sorted(labels.items())]
        return f"{name}{{{','.join(label_pairs)}}} {value}"
    return f"{name} {value}"


@router.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
def metrics(session: Session = Depends(get_session)) -> PlainTextResponse:
    status_counts_stmt = (
        select(RunImage.status, func.count())
        .select_from(RunImage)
        .group_by(RunImage.status)
    )
    status_counts = {
        row.status: int(row.count)
        for row in session.execute(status_counts_stmt).all()
    }

    approved_count = status_counts.get(RunImageStatus.APPROVED, 0)
    posted_count = status_counts.get(RunImageStatus.POSTED, 0)

    scheduled_count_stmt = (
        select(func.count())
        .select_from(RunImage)
        .where(
            RunImage.status == RunImageStatus.APPROVED,
            RunImage.scheduled_time.is_not(None),
        )
    )
    scheduled_count = int(session.execute(scheduled_count_stmt).scalar_one() or 0)

    runs_need_review_stmt = (
        select(func.count(func.distinct(RunImage.run_id)))
        .select_from(RunImage)
        .join(Run, Run.id == RunImage.run_id)
        .where(RunImage.status == RunImageStatus.GENERATED, Run.status != RunStatus.POSTED)
    )
    runs_need_review = int(session.execute(runs_need_review_stmt).scalar_one() or 0)

    lines = [
        "# HELP workflow_images_total Count of images by state.",
        "# TYPE workflow_images_total gauge",
        _format_metric("workflow_images_total", approved_count, {"state": "approved"}),
        _format_metric("workflow_images_total", posted_count, {"state": "posted"}),
        _format_metric("workflow_images_total", scheduled_count, {"state": "scheduled"}),
        "# HELP workflow_runs_need_review Number of runs needing review.",
        "# TYPE workflow_runs_need_review gauge",
        _format_metric("workflow_runs_need_review", runs_need_review),
    ]
    payload = "\n".join(lines) + "\n"
    return PlainTextResponse(payload, media_type="text/plain; version=0.0.4")
