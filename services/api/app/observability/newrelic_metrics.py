from __future__ import annotations

import os
import time
from typing import Any

import httpx


def _api_key() -> str | None:
    """
    Returns a New Relic ingest API key suitable for Metric API.

    We support multiple env var names to match common deployments.
    """
    for k in ("NEW_RELIC_METRICS_API_KEY", "NEW_RELIC_LICENSE_KEY", "NEW_RELIC_API_KEY"):
        v = (os.environ.get(k) or "").strip()
        if v:
            return v
    return None


def _metric_api_url() -> str:
    # US: metric-api.newrelic.com; EU: metric-api.eu.newrelic.com
    host = (os.environ.get("NEW_RELIC_METRIC_API_HOST") or "metric-api.newrelic.com").strip()
    host = host.replace("https://", "").replace("http://", "").strip().rstrip("/")
    return f"https://{host}/metric/v1"


def _common_attributes() -> dict[str, Any]:
    # Prefer an explicit service name; fall back to something stable.
    service_name = (
        os.environ.get("WF_SERVICE_NAME")
        or os.environ.get("NEW_RELIC_APP_NAME")
        or os.environ.get("SERVICE_NAME")
        or "workflow-api"
    )
    return {"service.name": service_name}


def record_count(
    name: str,
    value: float = 1.0,
    *,
    attributes: dict[str, Any] | None = None,
) -> None:
    """
    Best-effort dispatch of a New Relic *count* metric.

    No-op unless a Metric API ingest key is present. Errors are swallowed on purpose.
    """
    key = _api_key()
    if not key:
        return

    attrs: dict[str, Any] = {}
    attrs.update(_common_attributes())
    if attributes:
        # Ensure JSON-serializable-ish values (avoid throwing).
        for k, v in attributes.items():
            if v is None:
                continue
            attrs[k] = v

    payload = [
        {
            "metrics": [
                {
                    "name": name,
                    "type": "count",
                    "value": float(value),
                    "timestamp": int(time.time()),
                    "attributes": attrs,
                }
            ]
        }
    ]

    try:
        httpx.post(
            _metric_api_url(),
            headers={"Api-Key": key, "Content-Type": "application/json"},
            json=payload,
            timeout=2.5,
        )
    except Exception:
        return

