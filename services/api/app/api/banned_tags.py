from __future__ import annotations

from fastapi import APIRouter

from ..config import get_settings
from ..services.banned_tags import load_banned_tags_from_file, parse_banned_tags

router = APIRouter(prefix="/banned-tags", tags=["banned-tags"])


@router.get("", response_model=list[str])
async def get_banned_tags() -> list[str]:
    """
    Returns the current banned tags list for workflow filtering.
    """
    settings = get_settings()
    from_file = load_banned_tags_from_file(settings.banned_tags_file)
    if from_file is not None:
        return from_file
    return parse_banned_tags(settings.banned_tags)

