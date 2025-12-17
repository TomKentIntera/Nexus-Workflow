from __future__ import annotations

from typing import Dict, List, Optional
import os

import httpx
from fastapi import FastAPI, HTTPException
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
async def get_runs() -> Dict[str, List[Dict]]:
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
