from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_session
from ..models import BannedTag
from ..schemas import BannedTagsUpsert
from ..services.banned_tags import normalize_tags

router = APIRouter(prefix="/banned-tags", tags=["banned-tags"])


@router.get("", response_model=list[str])
def get_banned_tags(session: Session = Depends(get_session)) -> list[str]:
    """
    Returns the current banned tags list for workflow filtering.

    Response is a plain JSON list, suitable for n8n consumption.
    """
    tags = session.execute(select(BannedTag.tag).order_by(BannedTag.tag.asc())).scalars().all()
    return [str(t) for t in tags]


@router.post("", response_model=list[str], status_code=status.HTTP_201_CREATED)
def add_banned_tags(
    payload: BannedTagsUpsert, session: Session = Depends(get_session)
) -> list[str]:
    """
    Idempotently add tags to the banned list.

    Returns the full banned-tag list after update.
    """
    incoming = normalize_tags(payload.tags or [])
    if not incoming:
        raise HTTPException(status_code=400, detail="No tags provided")

    existing = set(
        session.execute(select(BannedTag.tag).where(BannedTag.tag.in_(incoming))).scalars().all()
    )
    to_add = [t for t in incoming if t not in existing]
    for t in to_add:
        session.add(BannedTag(tag=t))

    session.commit()
    tags = session.execute(select(BannedTag.tag).order_by(BannedTag.tag.asc())).scalars().all()
    return [str(t) for t in tags]


@router.delete("/{tag}", response_model=list[str])
def delete_banned_tag(tag: str, session: Session = Depends(get_session)) -> list[str]:
    """
    Delete a banned tag by exact match.

    Returns the full banned-tag list after deletion.
    """
    tag = (tag or "").strip()
    if not tag:
        raise HTTPException(status_code=400, detail="Tag is required")

    row = session.execute(select(BannedTag).where(BannedTag.tag == tag)).scalar_one_or_none()
    if row:
        session.delete(row)
        session.commit()

    tags = session.execute(select(BannedTag.tag).order_by(BannedTag.tag.asc())).scalars().all()
    return [str(t) for t in tags]

