# Nexus-Workflow

Orchestrates an image-generation workflow built on n8n, FastAPI, MySQL, and MinIO, plus a lightweight Gradio reviewer UI for approving results.

## Services
- **api**: FastAPI backend that proxies platform requests and now manages run/image metadata, approvals, and webhook dispatches to n8n.
- **n8n**: Automation engine that triggers the Python generator script and reports results to the API.
- **reviewer**: Gradio-based UI for browsing runs, previewing images, and approving any subset of them.
- **mysql**: Shared relational database storing runs, images, and approval audit trails.
- **minio**: Object storage for generated assets; the generator uploads here so the reviewer can render thumbnails directly.

## Getting Started
1. Copy each service's `.env.example` to `.env` and tweak values as needed (API, reviewer, n8n script environment).
2. Ensure the MinIO bucket defined by `WF_MINIO_BUCKET` exists (`runs` by default). You can create it via the MinIO console at `http://localhost:9001/` after `docker compose up`.
3. Launch the stack: `docker compose up --build`.
4. Access the services:
   - FastAPI docs: http://localhost:8000/docs
   - n8n: http://localhost:5678/
   - Reviewer UI: http://localhost:7860/
   - MinIO console: http://localhost:9001/

## Workflow Overview
1. n8n calls `services/n8n/scripts/images/generate.py` with prompt parameters. The script generates `count` images, uploads them to MinIO (if configured), and prints a JSON summary.
2. n8n registers a run via `POST /runs`, then either attaches the image metadata in the same request or calls `POST /runs/{id}/images` when uploads finish.
3. Operators open the Reviewer UI, pick a run, view the 10 generated assets, and approve any subset. The UI calls `POST /runs/{run_id}/images/{image_id}/approve`.
4. The API records approval metadata and asynchronously notifies n8n (or any listener) via `WF_N8N_APPROVAL_WEBHOOK` so downstream automations can fire.

## Key API Endpoints
- `POST /runs` – create a run with optional images payload.
- `GET /runs` / `GET /runs/{id}` – list or detail with nested images.
- `POST /runs/{id}/images` – append additional images.
- `POST /runs/{id}/status` – update run lifecycle state.
- `POST /runs/{run_id}/images/{image_id}/approve` – mark an image as approved and trigger webhooks.

## Environment Highlights
### API (`services/api/.env`)
- `WF_DATABASE_URL=mysql+pymysql://workflow:workflow@mysql:3306/workflow`
- `WF_MINIO_ENDPOINT=http://minio:9000`
- `WF_MINIO_PUBLIC_ENDPOINT=http://localhost:9000` (used for reviewer URLs)
- `WF_MINIO_BUCKET=runs`
- `WF_N8N_APPROVAL_WEBHOOK=http://n8n:5678/webhook/approval`

### Reviewer (`services/reviewer/.env`)
- `REVIEWER_API_BASE_URL=http://api:8000`
- `REVIEWER_DEFAULT_APPROVER=reviewer`
- `REVIEWER_REQUEST_TIMEOUT=15`

### n8n Generator Script
Environment variables or CLI flags configure MinIO access: `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`, and `MINIO_PUBLIC_BASE`. See `services/n8n/scripts/images/generate.py` for full argument list.

## Database Schema
- `runs`: workflow metadata (prompt, status, JSON payload, timestamps).
- `run_images`: generated image rows tied to runs, including ordinal, asset URI, status, notes.
- `run_image_approvals`: audit records capturing reviewer, optional notes, webhook status, and retry bookkeeping.

Tables are auto-created at API startup; integrate Alembic later if you need versioned migrations.
