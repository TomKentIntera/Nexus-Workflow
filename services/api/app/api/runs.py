from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta
from typing import List, Sequence

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings
from ..database import get_session
from ..models import Run, RunImage, RunImageApproval, RunImageStatus, RunStatus
from ..schemas import (
    RunCreate,
    RunImageApprovalRequest,
    RunImageApprovalResponse,
    RunImageCreate,
    RunImageList,
    RunImageListItem,
    RunLeaseResponse,
    RunList,
    RunRead,
    RunUpdateStatus,
)

router = APIRouter(prefix="/runs", tags=["runs"])


def _get_run(session: Session, run_id: str) -> Run:
    run = session.get(Run, run_id, options=(selectinload(Run.images),))
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


def _get_run_image(session: Session, run_id: str, image_id: str) -> RunImage:
    stmt = (
        select(RunImage)
        .where(RunImage.id == image_id, RunImage.run_id == run_id)
        .options(selectinload(RunImage.run), selectinload(RunImage.approvals))
    )
    result = session.execute(stmt).scalar_one_or_none()
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run image not found")
    return result


def _parse_window_time(value: str, label: str) -> time:
    try:
        return time.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"{label} must be HH:MM or HH:MM:SS (got '{value}')."
        ) from exc


def _count_scheduled_for_day(session: Session, day: date) -> int:
    stmt = (
        select(func.count())
        .select_from(RunImage)
        .where(
            RunImage.scheduled_time.is_not(None),
            RunImage.status.in_([RunImageStatus.APPROVED, RunImageStatus.POSTED]),
            func.date(RunImage.scheduled_time) == day,
        )
    )
    return int(session.execute(stmt).scalar_one() or 0)


def _calculate_scheduled_time(session: Session) -> datetime:
    settings = get_settings()
    window_start = _parse_window_time(settings.posting_window_start, "WF_POSTING_WINDOW_START")
    window_end = _parse_window_time(settings.posting_window_end, "WF_POSTING_WINDOW_END")

    if window_end <= window_start:
        raise ValueError("WF_POSTING_WINDOW_END must be later than WF_POSTING_WINDOW_START.")

    max_posts_per_day = settings.max_posts_per_day
    if max_posts_per_day <= 0:
        raise ValueError("WF_MAX_POSTS_PER_DAY must be > 0.")

    delay_min = settings.schedule_delay_min
    delay_max = settings.schedule_delay_max
    if delay_min < 0 or delay_max < 0:
        raise ValueError("Schedule delays must be >= 0 minutes.")
    if delay_min > delay_max:
        raise ValueError("WF_SCHEDULE_DELAY_MIN must be <= WF_SCHEDULE_DELAY_MAX.")

    last_stmt = (
        select(func.max(RunImage.scheduled_time))
        .select_from(RunImage)
        .where(
            RunImage.scheduled_time.is_not(None),
            RunImage.status.in_([RunImageStatus.APPROVED, RunImageStatus.POSTED]),
        )
    )
    last_scheduled = session.execute(last_stmt).scalar_one()

    now = datetime.utcnow()
    base_time = max(last_scheduled, now) if last_scheduled else now

    delay_minutes = delay_min if delay_min == delay_max else random.randint(delay_min, delay_max)
    candidate = base_time + timedelta(minutes=delay_minutes)

    def _window_for(day: date) -> tuple[datetime, datetime]:
        return datetime.combine(day, window_start), datetime.combine(day, window_end)

    day = candidate.date()
    window_start_dt, window_end_dt = _window_for(day)
    if candidate < window_start_dt:
        candidate = window_start_dt
    if candidate > window_end_dt:
        day = day + timedelta(days=1)
        candidate = datetime.combine(day, window_start)

    while True:
        if _count_scheduled_for_day(session, day) < max_posts_per_day:
            window_start_dt, window_end_dt = _window_for(day)
            if candidate < window_start_dt:
                candidate = window_start_dt
            if candidate > window_end_dt:
                day = day + timedelta(days=1)
                candidate = datetime.combine(day, window_start)
                continue
            return candidate
        day = day + timedelta(days=1)
        candidate = datetime.combine(day, window_start)


@router.post("", response_model=RunRead, status_code=status.HTTP_201_CREATED)
def create_run(payload: RunCreate, session: Session = Depends(get_session)) -> Run:
    run = Run(
        workflow_id=payload.workflow_id,
        prompt=payload.prompt,
        parameter_blob=payload.parameter_blob,
        status=payload.status,
    )

    for image in payload.images:
        run.images.append(
            RunImage(
                ordinal=image.ordinal,
                asset_uri=image.asset_uri,
                thumb_uri=image.thumb_uri,
                notes=image.notes,
            )
        )

    session.add(run)
    session.commit()
    session.refresh(run)
    return run


@router.get("", response_model=RunList)
def list_runs(
    status_filter: RunStatus | None = Query(default=None, alias="status"),
    session: Session = Depends(get_session),
) -> RunList:
    needs_review = (
        select(RunImage.id)
        .where(
            RunImage.run_id == Run.id,
            RunImage.status == RunImageStatus.GENERATED,
        )
        .exists()
    )
    stmt = (
        select(Run)
        .options(selectinload(Run.images))
        .where(needs_review, Run.status != RunStatus.POSTED)
        .order_by(Run.created_at.desc())
    )
    if status_filter:
        stmt = stmt.where(Run.status == status_filter)
    runs: Sequence[Run] = session.execute(stmt).unique().scalars().all()
    return RunList(runs=runs)


@router.post("/lease", response_model=None, status_code=status.HTTP_200_OK)
def lease_run(session: Session = Depends(get_session)):
    """
    Lease the next queued run for image generation.
    
    Atomically claims a queued run by:
    - Finding the oldest QUEUED run with no active lease
    - Setting leased_until to now + 2 hours
    - Setting status to GENERATING
    - Returns 200 with run details, or 204 if no run available
    """
    now = datetime.utcnow()
    lease_duration = timedelta(hours=2)
    lease_until = now + lease_duration
    
    # Find the oldest QUEUED run with no active lease
    stmt = (
        select(Run)
        .where(
            Run.status == RunStatus.QUEUED,
            (Run.leased_until.is_(None)) | (Run.leased_until < now),
        )
        .order_by(Run.created_at.asc())
        .limit(1)
    )
    
    run = session.execute(stmt).scalar_one_or_none()
    
    if not run:
        # No run available - return 204
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    
    # Lease the run
    run.status = RunStatus.GENERATING
    run.leased_until = lease_until
    run.updated_at = now
    session.add(run)
    session.commit()
    session.refresh(run)
    
    # Count existing images
    images_stmt = select(func.count()).select_from(RunImage).where(RunImage.run_id == run.id)
    generated_images = int(session.execute(images_stmt).scalar_one() or 0)
    
    # Determine image_count from parameter_blob or default to 1
    image_count = 1
    if run.parameter_blob and isinstance(run.parameter_blob, dict):
        image_count = run.parameter_blob.get("image_count", 1)
    
    remaining_images = max(0, image_count - generated_images)
    
    return RunLeaseResponse(
        id=run.id,
        workflow_id=run.workflow_id,
        prompt=run.prompt,
        parameter_blob=run.parameter_blob,
        image_count=image_count,
        generated_images=generated_images,
        remaining_images=remaining_images,
        leased_until=lease_until,
    )


@router.get("/images", response_model=RunImageList)
def list_run_images(
    status: RunImageStatus | None = Query(default=None, alias="status"),
    scheduled_only: bool = Query(default=False),
    limit: int = Query(default=48, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> RunImageList:
    """
    List run images with optional filtering.
    
    - status: Filter by image status (e.g., POSTED, APPROVED, GENERATED)
    - scheduled_only: Only return images with scheduled_time set
    - limit: Number of images to return (1-200)
    - offset: Pagination offset
    """
    stmt = (
        select(RunImage, Run.prompt, Run.created_at.label("run_created_at"))
        .join(Run, Run.id == RunImage.run_id)
        .order_by(RunImage.created_at.desc())
    )
    
    # Apply filters
    if scheduled_only:
        stmt = stmt.where(RunImage.scheduled_time.is_not(None))
    
    if status:
        stmt = stmt.where(RunImage.status == status)
    
    # Get total count (before pagination)
    count_stmt = (
        select(func.count())
        .select_from(RunImage)
        .join(Run, Run.id == RunImage.run_id)
    )
    if scheduled_only:
        count_stmt = count_stmt.where(RunImage.scheduled_time.is_not(None))
    if status:
        count_stmt = count_stmt.where(RunImage.status == status)
    total = int(session.execute(count_stmt).scalar_one() or 0)
    
    # Apply pagination
    stmt = stmt.limit(limit).offset(offset)
    
    # Execute query
    results = session.execute(stmt).all()
    
    # Build response
    images = []
    for image, prompt, run_created_at in results:
        images.append(
            RunImageListItem(
                id=image.id,
                run_id=image.run_id,
                ordinal=image.ordinal,
                asset_uri=image.asset_uri,
                thumb_uri=image.thumb_uri,
                generated_by_machine_id=image.generated_by_machine_id,
                status=image.status,
                notes=image.notes,
                fanvue_uuid=image.fanvue_uuid,
                r34_uuid=image.r34_uuid,
                twitter_posted_time=image.twitter_posted_time,
                created_at=image.created_at,
                run_created_at=run_created_at,
                prompt=prompt,
                scheduled_time=image.scheduled_time,
            )
        )
    
    return RunImageList(
        images=images,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{run_id}", response_model=RunRead)
def get_run(run_id: str, session: Session = Depends(get_session)) -> Run:
    return _get_run(session, run_id)


@router.post("/{run_id}/status", response_model=RunRead)
def update_run_status(
    run_id: str,
    payload: RunUpdateStatus,
    session: Session = Depends(get_session),
) -> Run:
    run = _get_run(session, run_id)
    run.status = payload.status
    run.updated_at = datetime.utcnow()
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


@router.post("/{run_id}/images", response_model=RunRead)
def add_run_images(
    run_id: str,
    payload: List[RunImageCreate],
    session: Session = Depends(get_session),
) -> Run:
    run = _get_run(session, run_id)
    for image in payload:
        run.images.append(
            RunImage(
                ordinal=image.ordinal,
                asset_uri=image.asset_uri,
                thumb_uri=image.thumb_uri,
                notes=image.notes,
            )
        )
    run.updated_at = datetime.utcnow()
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


@router.post("/{run_id}/images/{image_id}/approve", response_model=RunImageApprovalResponse)
def approve_run_image(
    run_id: str,
    image_id: str,
    payload: RunImageApprovalRequest,
    session: Session = Depends(get_session),
) -> RunImageApprovalResponse:
    image = _get_run_image(session, run_id, image_id)
    image.status = RunImageStatus.APPROVED
    image.notes = payload.notes or image.notes
    image.run.updated_at = datetime.utcnow()
    image.run.status = RunStatus.APPROVED
    if image.scheduled_time is None:
        try:
            image.scheduled_time = _calculate_scheduled_time(session)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
            ) from exc

    approval = RunImageApproval(
        run_image=image,
        approved_by=payload.approved_by,
        notes=payload.notes,
    )
    session.add(approval)
    session.add(image)
    session.commit()
    session.refresh(approval)

    return RunImageApprovalResponse(
        approval_id=approval.id,
        image_id=image.id,
        webhook_status=approval.webhook_status.value,
    )
