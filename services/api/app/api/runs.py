from __future__ import annotations

from datetime import datetime, timedelta
import os
import time
from typing import Any, List, Sequence

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from ..database import get_session
from ..models import Run, RunImage, RunImageApproval, RunImageStatus, RunStatus
from ..schemas import (
    RunCreate,
    RunImageApprovalRequest,
    RunImageApprovalResponse,
    RunImageCreate,
    RunImageRead,
    RunList,
    RunLeaseResponse,
    RunRead,
    RunUpdateStatus,
)
from ..clients.minio_client import MinioConfigError, MinioPutError, put_object_bytes
from ..config import get_settings

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


def _extract_image_count(parameter_blob: Any | None) -> int:
    """Best-effort extraction of requested image count from the run's parameter_blob."""
    try:
        if isinstance(parameter_blob, dict):
            val = parameter_blob.get("image_count", 1)
        else:
            val = 1
        count = int(val) if val is not None else 1
        return max(count, 1)
    except Exception:
        return 1


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
                generated_by_machine_id=getattr(image, "generated_by_machine_id", None),
                notes=image.notes,
            )
        )

    session.add(run)
    session.commit()
    session.refresh(run)
    return run


@router.post("/lease", response_model=RunLeaseResponse)
def lease_next_run(session: Session = Depends(get_session)) -> RunLeaseResponse:
    """
    Lease the next available run for image generation.

    - Only considers runs with `status=queued` and `leased_until IS NULL`
    - Sets `leased_until = now + 2 hours`
    - Also transitions status to `generating` (so UIs reflect progress)
    """
    now = datetime.utcnow()
    lease_until = now + timedelta(hours=2)

    # Atomically claim a single queued run.
    base_stmt = (
        select(Run)
        .where(Run.status == RunStatus.QUEUED, Run.leased_until.is_(None))
        .order_by(Run.created_at.asc())
        .limit(1)
    )
    # Prefer SKIP LOCKED when supported (MySQL 8+), fall back gracefully otherwise.
    try:
        run = session.execute(base_stmt.with_for_update(skip_locked=True)).scalars().first()
    except Exception:
        run = session.execute(base_stmt.with_for_update()).scalars().first()
    if not run:
        return Response(status_code=status.HTTP_204_NO_CONTENT)  # type: ignore[return-value]

    run.leased_until = lease_until
    run.status = RunStatus.GENERATING
    run.updated_at = now
    session.add(run)
    session.commit()
    session.refresh(run)

    generated_images = (
        session.execute(select(func.count()).select_from(RunImage).where(RunImage.run_id == run.id))
        .scalar_one()
    )
    requested = _extract_image_count(run.parameter_blob)
    remaining = max(requested - int(generated_images or 0), 0)

    return RunLeaseResponse(
        id=run.id,
        workflow_id=run.workflow_id,
        prompt=run.prompt,
        parameter_blob=run.parameter_blob,
        image_count=requested,
        generated_images=int(generated_images or 0),
        remaining_images=remaining,
        leased_until=run.leased_until,
    )


@router.get("", response_model=RunList)
def list_runs(
    status_filter: RunStatus | None = Query(default=None, alias="status"),
    session: Session = Depends(get_session),
) -> RunList:
    queued_count_stmt = select(func.count()).select_from(Run).where(Run.status == RunStatus.QUEUED)
    queued_count = session.execute(queued_count_stmt).scalar_one()

    cutoff = datetime.utcnow() - timedelta(hours=1)
    images_generated_last_hour_stmt = (
        select(func.count())
        .select_from(RunImage)
        .where(RunImage.created_at >= cutoff)
    )
    images_generated_last_hour = session.execute(images_generated_last_hour_stmt).scalar_one()

    stmt = select(Run).options(selectinload(Run.images)).order_by(Run.created_at.desc())
    if status_filter:
        stmt = stmt.where(Run.status == status_filter)
    else:
        # Default behavior: only return runs that are actively generating or have generated images.
        stmt = stmt.where(Run.status.in_([RunStatus.GENERATING, RunStatus.READY]))
    # Exclude runs with POSTED status
    stmt = stmt.where(Run.status != RunStatus.POSTED)
    runs: Sequence[Run] = session.execute(stmt).unique().scalars().all()
    return RunList(
        runs=runs,
        queued_count=queued_count,
        images_generated_last_hour=images_generated_last_hour,
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
    if payload.status in (RunStatus.READY, RunStatus.ERROR, RunStatus.APPROVED, RunStatus.POSTED):
        run.leased_until = None
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
                generated_by_machine_id=getattr(image, "generated_by_machine_id", None),
                notes=image.notes,
            )
        )
    run.updated_at = datetime.utcnow()
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


@router.post(
    "/{run_id}/images/upload",
    response_model=RunImageRead,
    status_code=status.HTTP_201_CREATED,
)
def upload_run_image(
    run_id: str,
    ordinal: int = Query(..., ge=1, description="1-indexed position within the run"),
    x_machine_id: str | None = Header(default=None, alias="X-Machine-Id"),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> RunImage:
    """
    Upload a generated image to MinIO and create the corresponding RunImage row.
    """
    run = _get_run(session, run_id)

    data = file.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    # Best-effort extension handling
    filename = (file.filename or "image").strip() or "image"
    _, ext = os.path.splitext(filename)
    if not ext:
        ext = ".png"

    object_name = f"{run_id}/{int(time.time())}_{ordinal}{ext}"
    try:
        put_object_bytes(object_name=object_name, data=data, content_type=file.content_type)
    except MinioConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except MinioPutError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    bucket = get_settings().minio_bucket
    asset_uri = f"s3://{bucket}/{object_name}"
    img = RunImage(
        run_id=run_id,
        ordinal=ordinal,
        asset_uri=asset_uri,
        thumb_uri=None,
        generated_by_machine_id=(x_machine_id.strip() if x_machine_id else None),
        status=RunImageStatus.GENERATED,
        notes=None,
    )
    run.updated_at = datetime.utcnow()

    session.add(img)
    session.add(run)
    session.commit()
    session.refresh(img)
    return img


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
        webhook_status="disabled",
    )


@router.post("/{run_id}/images/{image_id}/reject", response_model=dict)
def reject_run_image(
    run_id: str,
    image_id: str,
    payload: RunImageApprovalRequest,
    session: Session = Depends(get_session),
) -> dict:
    """Reject a run image."""
    image = _get_run_image(session, run_id, image_id)
    image.status = RunImageStatus.REJECTED
    image.notes = payload.notes or image.notes
    image.run.updated_at = datetime.utcnow()
    session.add(image)
    session.commit()
    session.refresh(image)
    
    return {
        "image_id": image.id,
        "status": image.status.value,
        "message": "Image rejected successfully"
    }