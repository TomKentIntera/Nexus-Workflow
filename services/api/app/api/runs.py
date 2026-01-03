from __future__ import annotations

from datetime import datetime
from typing import List, Sequence

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..database import get_session
from ..models import Run, RunImage, RunImageApproval, RunImageStatus, RunStatus
from ..schemas import (
    RunCreate,
    RunImageApprovalRequest,
    RunImageApprovalResponse,
    RunImageCreate,
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
    queued_count_stmt = select(func.count()).select_from(Run).where(Run.status == RunStatus.QUEUED)
    queued_count = session.execute(queued_count_stmt).scalar_one()

    stmt = select(Run).options(selectinload(Run.images)).order_by(Run.created_at.desc())
    if status_filter:
        stmt = stmt.where(Run.status == status_filter)
    else:
        # Default behavior: only return runs that are actively generating or have generated images.
        stmt = stmt.where(Run.status.in_([RunStatus.GENERATING, RunStatus.READY]))
    # Exclude runs with POSTED status
    stmt = stmt.where(Run.status != RunStatus.POSTED)
    runs: Sequence[Run] = session.execute(stmt).unique().scalars().all()
    return RunList(runs=runs, queued_count=queued_count)


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