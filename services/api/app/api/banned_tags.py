from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_session
from ..models import BannedTag, Run, RunStatus
from ..schemas import BannedTagsUpsert
from ..services.banned_tags import normalize_tags

router = APIRouter(prefix="/banned-tags", tags=["banned-tags"])


def _iter_strings(obj: object) -> list[str]:
    """
    Best-effort extraction of string values from nested JSON-like objects.
    """
    out: list[str] = []
    if obj is None:
        return out
    if isinstance(obj, str):
        out.append(obj)
        return out
    if isinstance(obj, dict):
        for v in obj.values():
            out.extend(_iter_strings(v))
        return out
    if isinstance(obj, (list, tuple, set)):
        for v in obj:
            out.extend(_iter_strings(v))
        return out
    return out


def _tokenize_tags(s: str) -> list[str]:
    # Many prompts/tags are comma/newline separated
    parts: list[str] = []
    for raw in s.replace("\n", ",").split(","):
        t = raw.strip()
        if t:
            parts.append(t)
    return parts


def _run_contains_tag(run: Run, tag: str) -> bool:
    """
    Returns True if the run appears to include the tag (case-insensitive),
    either in the prompt (comma-separated) or inside parameter_blob strings/lists.
    """
    target = tag.casefold()

    # Prompt is usually the canonical comma-separated tag string
    for tok in _tokenize_tags(run.prompt or ""):
        if tok.casefold() == target:
            return True

    blob = run.parameter_blob
    # If parameter_blob contains a tags list or any strings, inspect them.
    for s in _iter_strings(blob):
        for tok in _tokenize_tags(s):
            if tok.casefold() == target:
                return True

    return False


def _purge_queued_runs_for_tags(session: Session, tags: list[str]) -> int:
    """
    Delete queued runs that contain any of the provided tags.
    Returns number of runs deleted.
    """
    if not tags:
        return 0
    if not any(t.strip() for t in tags):
        return 0

    queued = session.execute(select(Run).where(Run.status == RunStatus.QUEUED)).scalars().all()
    deleted = 0
    for run in queued:
        if any(_run_contains_tag(run, t) for t in tags):
            session.delete(run)
            deleted += 1
    return deleted


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

    # Ensure new tags are present before purging runs.
    session.flush()

    # When banning a tag, remove any queued runs that contain it.
    _purge_queued_runs_for_tags(session=session, tags=to_add)

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

