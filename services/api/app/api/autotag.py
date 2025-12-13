from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..clients.minio_client import MinioConfigError, MinioFetchError, get_object_bytes
from ..services.wd14_tagger import WD14TaggerError, wd14_autotag

router = APIRouter(prefix="/autotag", tags=["autotag"])


def _validate_relative_path(path: str) -> str:
    p = (path or "").strip()
    if not p:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="path is required")
    # "relative path" guardrails
    if p.startswith("/") or p.startswith("http://") or p.startswith("https://"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="path must be a relative object key (not an absolute path or URL)",
        )
    if ".." in p.split("/"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="path must not contain '..' segments",
        )
    return p


class AutotagRequest(BaseModel):
    path: str = Field(..., description="Relative object key inside the configured MinIO bucket")
    general_threshold: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Override general tag threshold"
    )
    character_threshold: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Override character tag threshold"
    )
    include_ratings: bool = Field(default=False, description="Include rating:* tags in output")


class AutotagResponse(BaseModel):
    model: str
    bucket: str
    path: str
    tags: list[str]


@router.post("", response_model=AutotagResponse)
def autotag(payload: AutotagRequest) -> AutotagResponse:
    object_name = _validate_relative_path(payload.path)

    try:
        obj = get_object_bytes(object_name=object_name)
    except MinioConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except MinioFetchError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        tags = wd14_autotag(
            obj.data,
            general_threshold=payload.general_threshold,
            character_threshold=payload.character_threshold,
            include_ratings=payload.include_ratings,
        )
    except WD14TaggerError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return AutotagResponse(
        model="wd-v1-4-convnext-tagger",
        bucket=obj.bucket,
        path=obj.object_name,
        tags=[t.name for t in tags],
    )

