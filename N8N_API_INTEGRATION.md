# n8n API Integration Guide

## API Base URL

From within n8n (running in Docker), the API is accessible at:
```
http://api:8000
```

The API service is on the same Docker network (`workflow_stack`), so you can use the service name `api` instead of `localhost`.

## Available Endpoints

### Link Submissions (Mobile Link Submitter)

This is the “phone → submit a URL → n8n workflow continues processing” path.

**Endpoint:** `POST http://api:8000/links`

**Request Body:**
```json
{
  "url": "https://example.com/some/page",
  "source_url": "https://optional-source.example.com/"
}
```

**Response (always 201; webhook delivery is recorded):**
```json
{
  "id": "submission-uuid",
  "url": "https://example.com/some/page",
  "source_url": "https://optional-source.example.com/",
  "created_at": "2026-01-03T00:00:00",
  "webhook_status": "sent",
  "webhook_attempts": 1,
  "webhook_last_error": null
}
```

**Required env var (API → n8n):**
- `WF_N8N_LINK_SUBMISSION_WEBHOOK=http://n8n:5678/webhook/link-submission`

In n8n, create a workflow that starts with a **Webhook** node (POST) and use the resulting webhook URL for `WF_N8N_LINK_SUBMISSION_WEBHOOK`.

### 1. Create a Run (Queue Image Generation)
**Endpoint:** `POST http://api:8000/runs`

**Request Body:**
```json
{
  "workflow_id": "optional-workflow-id",
  "prompt": "your prompt text here",
  "status": "queued",
  "parameter_blob": {
    "width": 1024,
    "height": 1408,
    "image_count": 10,
    "orientation": "portrait",
    "negative_prompt": "optional negative prompt",
    "num_inference_steps": 30,
    "guidance_scale": 7.5,
    "seed": null,
    "saturation": 1.0,
    "contrast": 1.0,
    "prompt_array": ["tag1", "tag2", "tag3"],
    "original_tags": {
      "artist": ["artist1"],
      "series": ["series1"],
      "general": ["tag1", "tag2"],
      "character": ["character1"]
    },
    "prompt_string": "tag1, tag2, tag3"
  },
  "images": []
}
```

**Response:**
```json
{
  "id": "run-uuid",
  "workflow_id": "optional-workflow-id",
  "prompt": "your prompt text here",
  "status": "queued",
  "parameter_blob": { ... },
  "created_at": "2024-01-01T00:00:00",
  "updated_at": "2024-01-01T00:00:00",
  "images": []
}
```

**Status Values:**
- `queued` - Run is queued for image generation
- `generating` - Images are being generated
- `ready` - Images have been generated
- `approved` - Run has been approved
- `error` - An error occurred

### 2. List Runs
**Endpoint:** `GET http://api:8000/runs`

**Default Behavior:**
- If `status` is not provided, the API returns only `generating` and `ready` runs (to avoid returning large queued backlogs).
- The response includes `queued_count` so UIs can show how many runs are currently queued without fetching them all.

**Query Parameters:**
- `status` (optional) - Filter by status: `queued`, `generating`, `ready`, `approved`, `error`

**Example:** `GET http://api:8000/runs?status=ready`

**Response:**
```json
{
  "queued_count": 123,
  "runs": [
    {
      "id": "run-uuid",
      "prompt": "...",
      "status": "ready",
      "images": [...],
      ...
    }
  ]
}
```

### 3. Get a Specific Run
**Endpoint:** `GET http://api:8000/runs/{run_id}`

**Response:**
```json
{
  "id": "run-uuid",
  "prompt": "...",
  "status": "ready",
  "images": [
    {
      "id": "image-uuid",
      "ordinal": 1,
      "asset_uri": "s3://runs/run-id/timestamp.png",
      "status": "generated",
      ...
    }
  ],
  ...
}
```

### 4. Update Run Status
**Endpoint:** `POST http://api:8000/runs/{run_id}/status`

**Request Body:**
```json
{
  "status": "ready"
}
```

### 5. Add Images to a Run
**Endpoint:** `POST http://api:8000/runs/{run_id}/images`

**Request Body:**
```json
[
  {
    "ordinal": 1,
    "asset_uri": "s3://runs/run-id/image1.png",
    "thumb_uri": "s3://runs/run-id/thumb1.png",
    "notes": "optional notes"
  }
]
```

### 6. Approve an Image
**Endpoint:** `POST http://api:8000/runs/{run_id}/images/{image_id}/approve`

**Request Body:**
```json
{
  "approved_by": "user",
  "notes": "optional notes"
}
```

### 7. Reject an Image
**Endpoint:** `POST http://api:8000/runs/{run_id}/images/{image_id}/reject`

**Request Body:**
```json
{
  "approved_by": "user",
  "notes": "optional notes"
}
```

## n8n Configuration

### Using HTTP Request Node

1. **Add HTTP Request Node** to your n8n workflow

2. **Configure the node:**
   - **Method:** `POST` (or `GET` depending on endpoint)
   - **URL:** `http://api:8000/runs` (or the specific endpoint)
   - **Authentication:** None (API doesn't require auth currently)
   - **Send Headers:** 
     - `Content-Type: application/json`
   - **Send Body:** 
     - Select "JSON"
     - Enter the request body as shown above

3. **Example: Create a Queued Run**

   In the HTTP Request node:
   - **Method:** `POST`
   - **URL:** `http://api:8000/runs`
   - **Send Body (JSON):**
   ```json
   {
     "prompt": "{{ $json.prompt }}",
     "status": "queued",
     "parameter_blob": {
       "width": {{ $json.width }},
       "height": {{ $json.height }},
       "image_count": {{ $json.image_count }},
       "orientation": "{{ $json.orientation }}",
       "prompt_string": "{{ $json.prompt_string }}"
     }
   }
   ```

### Workflow Example: Queue Image Generation

1. **Trigger Node** (e.g., Webhook, Schedule, Manual)
2. **HTTP Request Node** - Create Run
   - Method: `POST`
   - URL: `http://api:8000/runs`
   - Body: JSON with prompt and parameters
3. **Wait/Poll Node** (optional) - Wait for generation to complete
4. **HTTP Request Node** - Get Run Status
   - Method: `GET`
   - URL: `http://api:8000/runs/{{ $json.id }}`
5. **Conditional Node** - Check if status is "ready"
6. **Process Results** - Use the generated images

### Important Notes

1. **Status Flow:**
   - When you create a run with `status: "queued"`, the image-generator worker will:
     - Change status to `generating`
     - Generate images
     - Change status to `ready` when complete
     - Change status to `error` if generation fails

2. **Parameter Blob:**
   - The `parameter_blob` field stores all generation parameters
   - The image-generator worker reads `image_count`, `width`, `height`, etc. from this field
   - You can store any additional metadata here

3. **Image URIs:**
   - Generated images are stored in MinIO
   - The `asset_uri` will be in format: `s3://runs/{run_id}/{timestamp}.png`
   - Use the reviewer app or the proxy endpoint to view images

4. **Network Access:**
   - From n8n container: Use `http://api:8000`
   - From your local machine: Use `http://localhost:8000`
   - The API is also accessible via the reviewer app at `http://localhost:7860/api/runs`

## Testing the API

You can test the API using curl from your local machine:

```bash
# Create a run
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "test prompt",
    "status": "queued",
    "parameter_blob": {
      "width": 1024,
      "height": 1408,
      "image_count": 5
    }
  }'

# List runs
curl http://localhost:8000/runs

# Get a specific run
curl http://localhost:8000/runs/{run_id}

# Autotag an image
curl -X POST http://localhost:8000/autotag \
  -H "Content-Type: application/json" \
  -d '{
    "path": "runs/run-id/image.png",
    "general_threshold": 0.35,
    "character_threshold": 0.35,
    "include_ratings": false
  }'
```

## Autotag Endpoints

### Autotag an Image
**Endpoint:** `POST http://api:8000/autotag`

This endpoint uses WD14 (SmilingWolf wd-v1-4-convnext-tagger) to automatically tag images stored in MinIO.

**Request Body:**
```json
{
  "path": "runs/run-id/image.png",
  "general_threshold": 0.35,
  "character_threshold": 0.35,
  "include_ratings": false
}
```

**Parameters:**
- `path` (required): Relative object key inside the configured MinIO bucket (e.g., `runs/run-id/image.png`)
  - Must be a relative path (not starting with `/`, `http://`, or `https://`)
  - Must not contain `..` segments
- `general_threshold` (optional): Confidence threshold for general tags (0.0-1.0). Defaults to configured value.
- `character_threshold` (optional): Confidence threshold for character tags (0.0-1.0). Defaults to configured value.
- `include_ratings` (optional): Whether to include rating tags (rating:safe, rating:questionable, rating:explicit). Default: `false`

**Response:**
```json
{
  "model": "wd-v1-4-convnext-tagger",
  "bucket": "runs",
  "path": "runs/run-id/image.png",
  "tags": ["tag1", "tag2", "tag3", ...]
}
```

**Example Usage in n8n:**

1. **HTTP Request Node:**
   - **Method:** `POST`
   - **URL:** `http://api:8000/autotag`
   - **Send Body (JSON):**
   ```json
   {
     "path": "{{ $json.image_path }}",
     "general_threshold": 0.35,
     "character_threshold": 0.35,
     "include_ratings": false
   }
   ```

2. **Example Workflow:**
   - Get image path from a run
   - Call autotag endpoint
   - Use tags to update metadata or filter images

**Error Responses:**
- `422 Unprocessable Entity`: Invalid path format (absolute path, URL, or contains `..`)
- `404 Not Found`: Image not found in MinIO
- `500 Internal Server Error`: MinIO configuration error or tagging service error

**Notes:**
- The path should be relative to the MinIO bucket root
- For images generated by the image-generator, paths are typically in format: `{run_id}/{timestamp}.png`
- The autotag service must be properly configured with MinIO credentials
- The WD14 model is loaded on first use and cached for subsequent requests

## API Documentation

FastAPI automatically generates interactive API documentation:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

You can use these to explore all available endpoints and test them directly.

