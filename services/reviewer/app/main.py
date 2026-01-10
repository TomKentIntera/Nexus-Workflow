from __future__ import annotations

from typing import Dict, List, Optional
from urllib.parse import urlencode, urljoin
import os
import re
import secrets
import logging
import sys
import uuid

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from minio import Minio
from minio.error import S3Error
from pydantic import BaseModel, Field

from .config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

settings = get_settings()
app = FastAPI(title="Reviewer UI", version="0.2.0")

# Enable CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_minio_client() -> Optional[Minio]:
    """Get MinIO client if configured."""
    endpoint = os.environ.get("MINIO_ENDPOINT")
    access_key = os.environ.get("MINIO_ACCESS_KEY")
    secret_key = os.environ.get("MINIO_SECRET_KEY")
    
    if endpoint and access_key and secret_key:
        try:
            # Remove protocol if present
            if "://" in endpoint:
                endpoint = endpoint.split("://")[1]
            return Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=False)
        except Exception as e:
            print(f"Warning: Failed to create MinIO client: {e}")
            return None
    return None


@app.get("/api/images/{bucket}/{path:path}", tags=["api"])
async def proxy_image(bucket: str, path: str):
    """Proxy MinIO images with authentication."""
    minio_client = get_minio_client()
    if not minio_client:
        raise HTTPException(status_code=503, detail="MinIO not configured")
    
    try:
        from io import BytesIO
        response = minio_client.get_object(bucket, path)
        # Read the entire object into memory (for small images this is fine)
        image_data = response.read()
        response.close()
        response.release_conn()
        
        # Determine content type from file extension
        content_type = "image/png"
        if path.lower().endswith(('.jpg', '.jpeg')):
            content_type = "image/jpeg"
        elif path.lower().endswith('.gif'):
            content_type = "image/gif"
        elif path.lower().endswith('.webp'):
            content_type = "image/webp"
        
        return StreamingResponse(
            BytesIO(image_data),
            media_type=content_type,
            headers={
                "Cache-Control": "public, max-age=3600",
                "Content-Length": str(len(image_data))
            }
        )
    except S3Error as e:
        if e.code == "NoSuchKey":
            raise HTTPException(status_code=404, detail=f"Image not found: {path}")
        raise HTTPException(status_code=500, detail=f"MinIO error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching image: {e}")


def _api_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=settings.api_base_url, timeout=settings.request_timeout)


def _rule34_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=settings.rule34_base_url, timeout=settings.request_timeout)


def _dedupe_preserve_order(values: List[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for v in values:
        key = v.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(v.strip())
    return out


def _tagify(tag: str) -> str:
    """
    Convert a tag to r34.nexus format: remove spaces and non-alphanumeric characters.
    Example: "cat girl" -> "catgirl", "69" -> "69"
    """
    # Remove all spaces and non-alphanumeric characters except numbers
    tagified = re.sub(r'[^a-zA-Z0-9]', '', tag.strip())
    return tagified.lower() if tagified else ""


_RE_BOY_GIRL = re.compile(r"^\d+(?:boy|girl|boys|girls)$", re.IGNORECASE)


def _is_common_general_tag(tag: str) -> bool:
    t = (tag or "").strip().lower()
    if not t:
        return True
    if _RE_BOY_GIRL.fullmatch(t):
        return True
    if "hair" in t or "eyes" in t:
        return True
    return False


class Rule34TagSearchResponse(BaseModel):
    data: List[Dict] = Field(default_factory=list)


@app.get("/api/rule34/tags/search", tags=["api"])
async def rule34_tag_search(
    query: str | None = Query(default=None),
    type: str | None = Query(default=None, description="Optional tag type filter (e.g. general, character)"),
    limit: int = Query(default=15, ge=1, le=50),
) -> Dict:
    """
    Proxy tag search requests to rule34.nexus API.
    
    - With query: GET https://rule34.nexus/api/tags/search?query=...&limit=...
    - Without query: GET https://rule34.nexus/api/tags/related?limit=...
    
    Returns the response from Rule34 API as-is.
    """
    q = (query or "").strip()
    type_filter = (type or "").strip().lower() or None
    has_query = bool(q)
    
    try:
        client = httpx.AsyncClient(
            base_url=settings.rule34_base_url, 
            timeout=settings.request_timeout,
            follow_redirects=True
        )
        try:
            if has_query:
                # Has query - use /api/tags/search with just query and limit
                params = {"query": q, "limit": limit}
                if type_filter:
                    # Forward to Rule34 API (it may ignore this) and also filter locally below.
                    params["type"] = type_filter
                endpoint = "/api/tags/search"
                logger.info(f"Proxying to Rule34 API: {settings.rule34_base_url}{endpoint} with params: {params}")
                res = await client.get(endpoint, params=params)
            else:
                # No query - use /api/tags/related for top tags
                params = {"limit": limit}
                if type_filter:
                    params["type"] = type_filter
                endpoint = "/api/tags/related"
                logger.info(f"Proxying to Rule34 API: {settings.rule34_base_url}{endpoint} with params: {params}")
                res = await client.get(endpoint, params=params)
            
            res.raise_for_status()
            payload = res.json()
            # Apply type filtering locally (rule34.nexus does not reliably filter by query params).
            if type_filter and isinstance(payload, dict) and isinstance(payload.get("data"), list):
                filtered: list[dict] = []
                for item in payload["data"]:
                    if not isinstance(item, dict):
                        continue
                    item_type = str(item.get("type", "")).strip().lower()
                    if item_type == type_filter:
                        filtered.append(item)
                payload = dict(payload)
                payload["data"] = filtered[:limit]
            return payload
        finally:
            await client.aclose()
    except httpx.ConnectError as exc:
        error_msg = f"Cannot connect to Rule34 API at {settings.rule34_base_url}. Error: {str(exc)}"
        logger.error(f"Rule34 connection error: {error_msg}")
        raise HTTPException(status_code=502, detail=error_msg)
    except httpx.HTTPStatusError as exc:
        error_msg = f"Rule34 API returned error {exc.response.status_code}: {exc.response.text[:200]}"
        logger.error(f"Rule34 HTTP error: {error_msg}")
        raise HTTPException(status_code=502, detail=error_msg)
    except httpx.HTTPError as exc:
        error_msg = f"Rule34 tag search failed: {str(exc)}"
        logger.error(f"Rule34 HTTP error: {error_msg}")
        raise HTTPException(status_code=502, detail=error_msg)
    except Exception as exc:
        error_msg = f"Unexpected error in Rule34 tag search: {type(exc).__name__}: {str(exc)}"
        logger.exception("Unexpected error in Rule34 tag search")
        raise HTTPException(status_code=502, detail=error_msg)


@app.get("/api/rule34/posts", tags=["api"])
async def rule34_posts(
    tags: str = Query("", description="Space-separated tags"),
    limit: int = Query(default=50, ge=1, le=200),
) -> Dict:
    """Proxy post search to rule34.nexus (list endpoint; does not include tags)."""
    try:
        async with _rule34_client() as client:
            res = await client.get("/api/posts", params={"tags": tags, "limit": limit})
            res.raise_for_status()
            return res.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Rule34 posts search failed: {exc}")


@app.get("/api/rule34/posts/{post_id}", tags=["api"])
async def rule34_post_detail(post_id: int) -> Dict:
    """Proxy post detail to rule34.nexus (includes tag list)."""
    try:
        async with _rule34_client() as client:
            res = await client.get(f"/api/posts/{post_id}")
            res.raise_for_status()
            return res.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Rule34 post detail failed: {exc}")


class ManualStageRequest(BaseModel):
    general_tags: List[str] = Field(default_factory=list)
    character_tags: List[str] = Field(default_factory=list)


def _post_has_all_required_tags(post_tags: object, required: List[str], required_type: str | None = None) -> bool:
    """
    Best-effort check that a post's tags include all required tag names.
    Uses case-insensitive matching.
    If required_type is specified (e.g., "general"), only checks tags of that type.
    """
    if not required:
        return True
    tags = post_tags if isinstance(post_tags, list) else []
    present: set[str] = set()
    for t in tags:
        if not isinstance(t, dict):
            continue
        # If required_type is specified, only check tags of that type
        if required_type:
            tag_type = str(t.get("type", "")).strip().lower()
            if tag_type != required_type.lower():
                continue
        name = t.get("name")
        if isinstance(name, str) and name.strip():
            present.add(name.strip().casefold())
    for req in required:
        r = (req or "").strip()
        if not r:
            continue
        if r.casefold() not in present:
            return False
    return True


async def _fetch_banned_tags_casefolded() -> set[str]:
    try:
        async with _api_client() as client:
            res = await client.get("/banned-tags")
            res.raise_for_status()
            data = res.json()
            if not isinstance(data, list):
                return set()
            return {str(t).strip().casefold() for t in data if isinstance(t, str) and str(t).strip()}
    except Exception as exc:
        # Staging should still work even if API is temporarily unavailable.
        logger.warning(f"Failed to fetch banned tags from API service: {type(exc).__name__}: {exc}")
        return set()


@app.post("/api/manual-runs/stage", tags=["api"])
async def manual_stage_run(payload: ManualStageRequest) -> Dict:
    """
    Stage a manual run:
    1) Search posts by user-provided general tags
    2) Pick a random post
    3) Extract that post's general tags
    4) Remove common tags (1boy/1girl, any tag containing hair/eyes)
    5) Prepend character tags and return final prompt/tag list
    """
    general_tags = _dedupe_preserve_order([t for t in payload.general_tags if isinstance(t, str)])
    character_tags = _dedupe_preserve_order([t for t in payload.character_tags if isinstance(t, str)])
    if not general_tags:
        raise HTTPException(status_code=400, detail="At least one general tag is required to stage a run")

    # Only search posts using general tags (character tags are prepended later)
    # Tagify tags: remove spaces and non-alphanumeric, then join with commas
    tagified_tags = [_tagify(tag) for tag in general_tags]
    tagified_tags = [t for t in tagified_tags if t]  # Remove empty tags
    if not tagified_tags:
        raise HTTPException(status_code=400, detail="No valid general tags after tagification")
    
    # Join with comma for r34.nexus API format: filter[tags]=tag1,tag2,tag3
    tags_comma_separated = ",".join(tagified_tags)
    
    try:
        async with _rule34_client() as client:
            # r34.nexus uses filter[tags] parameter with comma-separated, tagified tags
            # The urlencode function will properly encode filter[tags] to filter%5Btags%5D
            # and commas in tag values will be encoded as %2C
            # Note: per_page maximum is 50
            params = {"filter[tags]": tags_comma_separated, "page": 1, "per_page": 50}
            # Build the full URL for logging with proper encoding
            search_url = urljoin(str(settings.rule34_base_url).rstrip('/') + '/', "api/posts")
            query_string = urlencode(params, doseq=False)
            full_url = f"{search_url}?{query_string}"
            logger.info(f"Staging manual run: searching posts at {full_url}")
            posts_res = await client.get("/api/posts", params=params)
            posts_res.raise_for_status()
            posts_payload = posts_res.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Rule34 posts search failed: {exc}")

    posts = posts_payload.get("data") if isinstance(posts_payload, dict) else None
    if not isinstance(posts, list) or not posts:
        raise HTTPException(status_code=404, detail="No posts found for those general tags")

    # Pick a random post that actually contains all requested tags.
    # rule34.nexus may return fallback results even for invalid/unknown tags, so verify via post detail.
    candidates = [p for p in posts if isinstance(p, dict) and "id" in p]
    if not candidates:
        raise HTTPException(status_code=502, detail="Unexpected Rule34 posts response shape")

    max_attempts = min(25, len(candidates))
    tried_ids: set[int] = set()
    post_id: int | None = None
    preview_url: str | None = None
    post_obj: Dict | None = None

    for _ in range(max_attempts):
        picked = secrets.choice(candidates)
        try:
            pid = int(picked["id"])
        except Exception:
            continue
        if pid in tried_ids:
            continue
        tried_ids.add(pid)

        preview_url = None
        try:
            media = picked.get("media") if isinstance(picked.get("media"), dict) else None
            if media:
                preview_url = media.get("preview_url") or media.get("thumb_url")
        except Exception:
            preview_url = None

        try:
            async with _rule34_client() as client:
                detail_res = await client.get(f"/api/posts/{pid}")
                detail_res.raise_for_status()
                detail_payload = detail_res.json()
        except httpx.HTTPError:
            continue

        obj = detail_payload.get("data") if isinstance(detail_payload, dict) else None
        if not isinstance(obj, dict):
            continue

        # Verify that the post has all required general tags as type "general"
        # Character tags are user-provided and will be prepended later, so we don't verify them here
        if _post_has_all_required_tags(obj.get("tags"), general_tags, required_type="general"):
            post_id = pid
            post_obj = obj
            break

    if post_id is None or post_obj is None:
        raise HTTPException(
            status_code=404,
            detail="No posts found that include all selected tags (tags may be invalid or too restrictive)",
        )

    tags = post_obj.get("tags")
    if not isinstance(tags, list):
        tags = []

    extracted_general: List[str] = []
    for t in tags:
        if not isinstance(t, dict):
            continue
        if str(t.get("type", "")).lower() != "general":
            continue
        name = t.get("name")
        if isinstance(name, str) and name.strip():
            # Convert r34.nexus tag format (tag_name) to space-separated format (tag name)
            # for comparison with banned tags which are in "tag name" format
            tag_with_spaces = name.strip().replace("_", " ")
            extracted_general.append(tag_with_spaces)

    cleaned_general = [t for t in extracted_general if not _is_common_general_tag(t)]
    cleaned_general = _dedupe_preserve_order(cleaned_general)

    # Save original character tags for response (before normalization)
    input_character_tags = list(character_tags)

    # Normalize character tags: convert underscores to spaces (in case user copied from r34.nexus)
    # This ensures consistent format for banned tag comparison
    character_tags = [tag.replace("_", " ") for tag in character_tags]

    # Normalize user's input general tags to space format for matching
    # (user tags might have underscores if copied from r34.nexus)
    normalized_input_general = [tag.replace("_", " ") for tag in general_tags]

    # Remove any tags that are banned.
    # Note: banned tags are in "tag name" format (with spaces), and we've converted
    # both r34.nexus tags and character tags from "tag_name" to "tag name" format above
    banned = await _fetch_banned_tags_casefolded()
    if banned:
        cleaned_general = [t for t in cleaned_general if t.casefold() not in banned]
        character_tags = [t for t in character_tags if t.casefold() not in banned]
        normalized_input_general = [t for t in normalized_input_general if t.casefold() not in banned]

    # Keep all user-input general tags that are present in the cleaned general tags
    # Match by casefolded comparison to handle case differences
    user_input_tags_set = {t.casefold() for t in normalized_input_general}
    user_tags_kept: List[str] = []
    other_tags: List[str] = []
    
    for tag in cleaned_general:
        if tag.casefold() in user_input_tags_set:
            user_tags_kept.append(tag)
        else:
            other_tags.append(tag)

    # Deduplicate user tags (in case of case variations) while preserving order
    user_tags_kept = _dedupe_preserve_order(user_tags_kept)

    # Randomly select from other tags to fill up to 10 total tags
    # Use secrets module for cryptographically secure random selection
    max_other_tags = max(0, 10 - len(user_tags_kept))
    if len(other_tags) > max_other_tags:
        selected_other_tags = secrets.SystemRandom().sample(other_tags, max_other_tags)
    else:
        selected_other_tags = other_tags

    # Combine: user input tags first, then randomly selected other tags
    cleaned_general = user_tags_kept + selected_other_tags

    # Finally, prepend character tags.
    final_tags = _dedupe_preserve_order(character_tags + cleaned_general)
    final_prompt = ", ".join(final_tags)

    if not final_tags:
        raise HTTPException(status_code=400, detail="All staged tags were removed (likely due to banned tags)")

    # Extract original tags: all r34.nexus tags go into "general", user character tags into "character"
    # Keep original underscore format from r34.nexus for original_tags
    original_tags: Dict[str, List[str]] = {
        "artist": [],
        "series": [],
        "general": [],
        "character": [],
    }
    
    # Put all tags from r34.nexus API into "general" (in original underscore format)
    # All tag types (artist, series, general, character) from r34 go into "general"
    for t in tags:
        if not isinstance(t, dict):
            continue
        name = t.get("name")
        if isinstance(name, str) and name.strip():
            # Keep original underscore format from r34.nexus
            tag_name = name.strip()
            if tag_name not in original_tags["general"]:
                original_tags["general"].append(tag_name)
    
    # Put user-provided character tags into "character" section
    # Convert space format to underscore format to match r34.nexus format
    # If the tag exists in r34.nexus tags, use the exact format from r34 (preserves casing)
    for char_tag in input_character_tags:
        if isinstance(char_tag, str) and char_tag.strip():
            # Convert to underscore format for comparison
            char_tag_underscore = char_tag.strip().replace(" ", "_")
            # Check if this tag exists in r34.nexus tags (use r34 format if found)
            found_in_r34 = False
            for r34_tag in original_tags["general"]:
                if r34_tag.lower() == char_tag_underscore.lower():
                    # Use the exact format from r34.nexus
                    if r34_tag not in original_tags["character"]:
                        original_tags["character"].append(r34_tag)
                    found_in_r34 = True
                    break
            if not found_in_r34:
                # Tag not in r34, use converted underscore format
                if not any(t.lower() == char_tag_underscore.lower() for t in original_tags["character"]):
                    original_tags["character"].append(char_tag_underscore)

    return {
        "input_general_tags": general_tags,
        "input_character_tags": input_character_tags,
        "selected_post": {
            "id": post_id,
            "preview_url": preview_url,
            "api_url": f"{settings.rule34_base_url.rstrip('/')}/api/posts/{post_id}",
        },
        "extracted_general_tags": extracted_general,
        "cleaned_general_tags": cleaned_general,
        "final_tags": final_tags,
        "final_prompt": final_prompt,
        "original_tags": original_tags,
    }


class ManualSubmitRequest(BaseModel):
    final_tags: List[str] = Field(default_factory=list)
    image_count: int = Field(default=10, ge=1, le=50)
    seed_post_id: int | None = None
    original_tags: Dict[str, List[str]] = Field(
        default_factory=lambda: {"artist": [], "series": [], "general": [], "character": []}
    )


@app.post("/api/manual-runs/submit", tags=["api"])
async def manual_submit_run(payload: ManualSubmitRequest) -> Dict:
    """
    Submit a staged manual run by creating a new Run in the workflow API.
    Creates a QUEUED run with parameter_blob containing all required fields.
    """
    final_tags = _dedupe_preserve_order([t for t in payload.final_tags if isinstance(t, str)])
    if not final_tags:
        raise HTTPException(status_code=400, detail="final_tags cannot be empty")

    # Randomly determine orientation and assign width/height accordingly
    # Portrait: 1024w x 1408h, Landscape: 1408w x 1024h
    orientation = secrets.choice(["portrait", "landscape"])
    if orientation == "portrait":
        width = 1024
        height = 1408
    else:  # landscape
        width = 1408
        height = 1024

    # Build parameter_blob with all required fields
    parameter_blob: Dict[str, object] = {
        "width": width,
        "height": height,
        "image_count": int(payload.image_count),
        "orientation": orientation,
        "prompt_array": final_tags,  # Array of tags
        "original_tags": payload.original_tags,  # Organized by type (artist, series, general, character)
        "prompt_string": ", ".join(final_tags),  # Comma-separated prompt string
        "watermark_width": 400,
        "source": "manual-reviewer",
    }
    
    if payload.seed_post_id is not None:
        parameter_blob["seed_post_id"] = int(payload.seed_post_id)

    # Generate UUID for workflow_id
    workflow_id = str(uuid.uuid4())

    run_create = {
        "workflow_id": workflow_id,
        "prompt": ", ".join(final_tags),
        "parameter_blob": parameter_blob,
        "status": "queued",
        "images": [],
    }

    try:
        async with _api_client() as client:
            res = await client.post("/runs", json=run_create)
            res.raise_for_status()
            return res.json()
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to API service at {settings.api_base_url}. Is the API service running?",
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to create run: {exc}")


@app.get("/api/runs", tags=["api"])
async def get_runs() -> Dict:
    """Get all runs."""
    try:
        async with _api_client() as client:
            response = await client.get("/runs")
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=503, 
            detail=f"Cannot connect to API service at {settings.api_base_url}. Is the API service running?"
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch runs: {exc}")


@app.get("/api/runs/{run_id}", tags=["api"])
async def get_run(run_id: str) -> Dict:
    """Get a specific run with images."""
    try:
        async with _api_client() as client:
            response = await client.get(f"/runs/{run_id}")
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Run not found")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch run: {exc}")


@app.get("/api/stats/images-per-hour", tags=["api"])
async def stats_images_per_hour(hours: int = 24) -> Dict:
    """Proxy stats endpoint from API service."""
    try:
        async with _api_client() as client:
            response = await client.get("/stats/images-per-hour", params={"hours": hours})
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to API service at {settings.api_base_url}. Is the API service running?",
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch stats: {exc}")


@app.get("/api/stats/reviewer-summary", tags=["api"])
async def reviewer_summary() -> Dict:
    """Proxy reviewer summary endpoint from API service."""
    try:
        async with _api_client() as client:
            response = await client.get("/stats/reviewer-summary")
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to API service at {settings.api_base_url}. Is the API service running?",
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch reviewer summary: {exc}")


@app.get("/api/stats/images-last-hour-by-machine", tags=["api"])
async def images_last_hour_by_machine() -> Dict:
    """Proxy last-hour-by-machine stats endpoint from API service."""
    try:
        async with _api_client() as client:
            response = await client.get("/stats/images-last-hour-by-machine")
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to API service at {settings.api_base_url}. Is the API service running?",
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch stats: {exc}")


@app.get("/api/run-images", tags=["api"])
async def list_run_images(
    status: str | None = Query(default=None), 
    scheduled_only: bool = Query(default=False), 
    limit: int = Query(default=48), 
    offset: int = Query(default=0)
) -> Dict:
    """Proxy run image listing endpoint from API service."""
    try:
        params: dict[str, object] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        # Pass scheduled_only - FastAPI expects lowercase "true" for boolean query params
        if scheduled_only:
            params["scheduled_only"] = "true"
        async with _api_client() as client:
            response = await client.get("/runs/images", params=params)
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to API service at {settings.api_base_url}. Is the API service running?",
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch run images: {exc}")


@app.post("/api/runs/{run_id}/images/{image_id}/approve", tags=["api"])
async def approve_image(run_id: str, image_id: str) -> Dict:
    """Approve an image."""
    try:
        async with _api_client() as client:
            response = await client.post(
                f"/runs/{run_id}/images/{image_id}/approve",
                json={"approved_by": "user", "notes": None},
            )
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=503, 
            detail=f"Cannot connect to API service at {settings.api_base_url}. Is the API service running?"
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to approve image: {exc}")


@app.post("/api/runs/{run_id}/images/{image_id}/reject", tags=["api"])
async def reject_image(run_id: str, image_id: str) -> Dict:
    """Reject an image."""
    try:
        async with _api_client() as client:
            response = await client.post(
                f"/runs/{run_id}/images/{image_id}/reject",
                json={"approved_by": "user", "notes": None},
            )
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=503, 
            detail=f"Cannot connect to API service at {settings.api_base_url}. Is the API service running?"
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to reject image: {exc}")


@app.post("/api/runs/{run_id}/generate-more", tags=["api"])
async def generate_more_images(run_id: str, payload: Dict) -> Dict:
    """Generate more images for a run."""
    try:
        async with _api_client() as client:
            response = await client.post(
                f"/runs/{run_id}/generate-more",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=503, 
            detail=f"Cannot connect to API service at {settings.api_base_url}. Is the API service running?"
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to generate more images: {exc}")


@app.get("/api/banned-tags", tags=["api"])
async def list_banned_tags() -> List[str]:
    """Proxy banned-tags list from API service."""
    try:
        async with _api_client() as client:
            response = await client.get("/banned-tags")
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to API service at {settings.api_base_url}. Is the API service running?",
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch banned tags: {exc}")


@app.post("/api/banned-tags", tags=["api"])
async def add_banned_tags(payload: Dict) -> List[str]:
    """Proxy add-banned-tags to API service."""
    try:
        async with _api_client() as client:
            response = await client.post("/banned-tags", json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to API service at {settings.api_base_url}. Is the API service running?",
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to add banned tags: {exc}")


@app.delete("/api/banned-tags/{tag}", tags=["api"])
async def delete_banned_tag(tag: str) -> List[str]:
    """Proxy delete-banned-tag to API service."""
    try:
        async with _api_client() as client:
            response = await client.delete(f"/banned-tags/{tag}")
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to API service at {settings.api_base_url}. Is the API service running?",
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to delete banned tag: {exc}")


@app.get("/api/allowed-search-tags", tags=["api"])
async def list_allowed_search_tags() -> List[Dict]:
    """Proxy allowed-search-tags list from API service."""
    try:
        async with _api_client() as client:
            response = await client.get("/allowed-search-tags")
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, list) else []
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to API service at {settings.api_base_url}. Is the API service running?",
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch allowed search tags: {exc}")


@app.post("/api/allowed-search-tags", tags=["api"])
async def add_allowed_search_tags(payload: Dict) -> List[Dict]:
    """Proxy add-allowed-search-tags to API service."""
    try:
        async with _api_client() as client:
            response = await client.post("/allowed-search-tags", json=payload)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, list) else []
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to API service at {settings.api_base_url}. Is the API service running?",
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to add allowed search tags: {exc}")


@app.delete("/api/allowed-search-tags/{tag_type}/{tag}", tags=["api"])
async def delete_allowed_search_tag(tag_type: str, tag: str) -> List[Dict]:
    """Proxy delete-allowed-search-tag to API service."""
    try:
        async with _api_client() as client:
            response = await client.delete(f"/allowed-search-tags/{tag_type}/{tag}")
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, list) else []
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to API service at {settings.api_base_url}. Is the API service running?",
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to delete allowed search tag: {exc}")


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the reviewer UI."""
    import os
    from pathlib import Path
    
    # Try to read from mounted static file first (dev mode)
    static_path = Path("/app/static/index.html")
    if static_path.exists():
        with open(static_path, "r", encoding="utf-8") as f:
            return f.read()
    
    # Fallback to embedded HTML (production mode)
    embedded_path = Path(__file__).parent.parent / "static" / "index.html"
    if embedded_path.exists():
        with open(embedded_path, "r", encoding="utf-8") as f:
            return f.read()
    
    # Last resort: return a simple error message
    return HTMLResponse(
        content="<h1>Error: index.html not found</h1>",
        status_code=500
    )
