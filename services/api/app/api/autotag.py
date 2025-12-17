from __future__ import annotations

import io
import os
from typing import Dict

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..clients.minio_client import MinioConfigError, MinioFetchError, get_object_bytes

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
    general_res: Dict[str, float] = Field(default_factory=dict, description="General tags with confidence scores")
    character_res: Dict[str, float] = Field(default_factory=dict, description="Character tags with confidence scores")
    rating: Dict[str, float] = Field(default_factory=dict, description="Rating scores (general, sensitive, questionable, explicit)")


@router.post("", response_model=AutotagResponse)
def autotag(payload: AutotagRequest) -> AutotagResponse:
    object_name = _validate_relative_path(payload.path)

    # Fetch image from MinIO
    try:
        obj = get_object_bytes(object_name=object_name)
    except MinioConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except MinioFetchError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Validate image data
    if not obj.data or len(obj.data) == 0:
        raise HTTPException(status_code=400, detail=f"Image file '{object_name}' is empty")
    
    if len(obj.data) < 100:  # Very small files are likely not valid images
        raise HTTPException(status_code=400, detail=f"Image file '{object_name}' is too small ({len(obj.data)} bytes)")

    # Get wd14-tagger service URL (default to service name in Docker network)
    wd14_tagger_url = os.environ.get("WD14_TAGGER_URL", "http://wd14-tagger:5010")
    
    # Check if wd14-tagger service is available (with shorter timeout to fail fast)
    try:
        with httpx.Client(timeout=2.0) as client:
            # Try to reach the service (wd14-tagger might not have /healthz, so try /docs or just catch the error)
            try:
                client.get(f"{wd14_tagger_url}/docs", timeout=2.0)
            except:
                # If /docs doesn't exist, that's fine - service might be running
                pass
    except (httpx.ConnectError, httpx.TimeoutException):
        raise HTTPException(
            status_code=503,
            detail="WD14-tagger service is not available. Please ensure the wd14-tagger service is running. Start it with: docker compose up -d wd14-tagger"
        ) from None
    
    # Prepare parameters for wd14-tagger-server
    params = {}
    if payload.general_threshold is not None:
        params["general_threshold"] = payload.general_threshold
    if payload.character_threshold is not None:
        params["character_threshold"] = payload.character_threshold
    
    # Call wd14-tagger-server
    try:
        with httpx.Client(timeout=60.0) as client:
            # Upload image as multipart/form-data
            files = {
                "file": (object_name.split("/")[-1], io.BytesIO(obj.data), obj.content_type or "image/png")
            }
            response = client.post(
                f"{wd14_tagger_url}/upload",
                params=params,
                files=files
            )
            response.raise_for_status()
            result = response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to call wd14-tagger service: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error processing image: {exc}") from exc

    # Extract tags from wd14-tagger-server response
    # The response format is: {"tag_result": "tag1, tag2, ...", "general_res": {...}, "character_res": {...}, "rating": {...}}
    tags = []
    if "tag_result" in result:
        # Parse comma-separated tags
        tags = [tag.strip() for tag in result["tag_result"].split(",") if tag.strip()]
    
    # Filter out rating tags if not requested
    if not payload.include_ratings:
        rating_tags = ["general", "sensitive", "questionable", "explicit", "rating:general", "rating:sensitive", "rating:questionable", "rating:explicit"]
        tags = [tag for tag in tags if tag.lower() not in rating_tags]

    # Extract general_res, character_res, and rating from the response
    general_res = result.get("general_res", {})
    character_res = result.get("character_res", {})
    rating = result.get("rating", {})

    return AutotagResponse(
        model="wd-v1-4-convnext-tagger",
        bucket=obj.bucket,
        path=obj.object_name,
        tags=tags,
        general_res=general_res,
        character_res=character_res,
        rating=rating,
    )

