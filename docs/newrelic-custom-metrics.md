# New Relic custom metrics (runs leased + images generated)

This repository emits **New Relic custom metrics** for two key events:

- **A run is leased** (a generator claims work)
- **An image is generated** (an image is uploaded to the API)

These are dispatched via the **New Relic Metric API** (HTTP ingest) from the API service.

## Metrics

### `wf.run.leased` (count)

Emitted when a queued run is leased via `POST /runs/lease`.

- **Attributes**
  - `run.id`
  - `run.workflow_id`
  - `machine.id` (from request header `X-Machine-Id`, if present)
  - `run.requested_images`
  - `run.remaining_images`

### `wf.image.generated` (count)

Emitted when an image is uploaded via `POST /runs/{run_id}/images/upload`.

- **Attributes**
  - `run.id`
  - `image.id`
  - `image.ordinal`
  - `machine.id` (from request header `X-Machine-Id`)

## How machine IDs are captured

- The image generator worker sends `X-Machine-Id` on:
  - lease calls (`POST /runs/lease`)
  - image upload calls (`POST /runs/{run_id}/images/upload`)
- The API stores `X-Machine-Id` on the image row (`generated_by_machine_id`) and uses it for the `wf.image.generated` metric attribute.

## Configuration

Metrics are a **best-effort no-op** unless an ingest key is configured.

Set one of:

- `NEW_RELIC_METRICS_API_KEY` (preferred name)
- `NEW_RELIC_LICENSE_KEY` (also supported)
- `NEW_RELIC_API_KEY` (also supported)

Optional:

- `NEW_RELIC_METRIC_API_HOST`
  - US (default): `metric-api.newrelic.com`
  - EU: `metric-api.eu.newrelic.com`
- `WF_SERVICE_NAME` (sent as `service.name` attribute; default: `workflow-api`)

Example (US):

```bash
export NEW_RELIC_LICENSE_KEY="…"
export NEW_RELIC_METRIC_API_HOST="metric-api.newrelic.com"
export WF_SERVICE_NAME="workflow-api"
```

## Implementation notes

- **API implementation**: `services/api/app/observability/newrelic_metrics.py`
- The Metric API call timeout is intentionally short and failures are swallowed so production traffic is not impacted by observability ingest issues.

