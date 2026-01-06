from __future__ import annotations

from typing import Dict, List, Optional
import os

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from minio import Minio
from minio.error import S3Error

from .config import get_settings

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
