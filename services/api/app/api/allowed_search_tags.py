from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_session
from ..models import AllowedSearchTag
from ..schemas import AllowedSearchTagItem, AllowedSearchTagRead, AllowedSearchTagsUpsert

router = APIRouter(prefix="/allowed-search-tags", tags=["allowed-search-tags"])


def _normalize_incoming(items: list[AllowedSearchTagItem]) -> list[tuple[str, str]]:
    """
    Normalize incoming items and de-dupe them (case-insensitive).
    Returns list of (type, tag).
    """
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in items or []:
        t = str(item.type.value).strip()
        tag = str(item.tag).strip()
        if not t:
            continue
        if not tag:
            continue
        key = (t.casefold(), tag.casefold())
        if key in seen:
            continue
        seen.add(key)
        out.append((t, tag))
    return out


@router.get("", response_model=list[AllowedSearchTagRead])
def list_allowed_search_tags(session: Session = Depends(get_session)) -> list[AllowedSearchTag]:
    """
    Returns allowed search tags used for "post search" / generation selection.
    """
    stmt = select(AllowedSearchTag).order_by(AllowedSearchTag.type.asc(), AllowedSearchTag.tag.asc())
    return list(session.execute(stmt).scalars().all())


@router.post("", response_model=list[AllowedSearchTagRead], status_code=status.HTTP_201_CREATED)
def add_allowed_search_tags(
    payload: AllowedSearchTagsUpsert,
    session: Session = Depends(get_session),
) -> list[AllowedSearchTag]:
    """
    Idempotently add (type, tag) pairs to the allowlist.
    Returns the full list after update.
    """
    incoming = _normalize_incoming(payload.tags)
    if not incoming:
        raise HTTPException(status_code=400, detail="No tags provided")

    types = sorted({t for (t, _tag) in incoming})
    tags = sorted({tag for (_t, tag) in incoming})

    existing_rows = session.execute(
        select(AllowedSearchTag.type, AllowedSearchTag.tag).where(
            AllowedSearchTag.type.in_(types),
            AllowedSearchTag.tag.in_(tags),
        )
    ).all()
    existing = {(str(t), str(tag)) for (t, tag) in existing_rows}

    to_add = [(t, tag) for (t, tag) in incoming if (t, tag) not in existing]
    for t, tag in to_add:
        session.add(AllowedSearchTag(type=t, tag=tag))

    session.commit()

    stmt = select(AllowedSearchTag).order_by(AllowedSearchTag.type.asc(), AllowedSearchTag.tag.asc())
    return list(session.execute(stmt).scalars().all())


@router.delete("/{tag_type}/{tag}", response_model=list[AllowedSearchTagRead])
def delete_allowed_search_tag(
    tag_type: str,
    tag: str,
    session: Session = Depends(get_session),
) -> list[AllowedSearchTag]:
    """
    Delete an allowed search tag by exact (type, tag) match.
    Returns the full list after deletion.
    """
    tag_type = (tag_type or "").strip()
    tag = (tag or "").strip()
    if not tag_type:
        raise HTTPException(status_code=400, detail="Type is required")
    if not tag:
        raise HTTPException(status_code=400, detail="Tag is required")

    row = session.execute(
        select(AllowedSearchTag).where(
            AllowedSearchTag.type == tag_type,
            AllowedSearchTag.tag == tag,
        )
    ).scalar_one_or_none()
    if row:
        session.delete(row)
        session.commit()

    stmt = select(AllowedSearchTag).order_by(AllowedSearchTag.type.asc(), AllowedSearchTag.tag.asc())
    return list(session.execute(stmt).scalars().all())

