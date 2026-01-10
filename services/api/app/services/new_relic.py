from __future__ import annotations

import threading
from typing import Any, Mapping

import httpx

from ..config import get_settings


def _resolve_events_url() -> tuple[str | None, str | None]:
    """
    Returns (url, insert_key) or (None, None) if not configured.

    We prefer `WF_NEW_RELIC_EVENTS_URL` when provided (supports EU region endpoints),
    otherwise fall back to the legacy Insights insert endpoint:
    https://insights-collector.newrelic.com/v1/accounts/{account_id}/events
    """
    settings = get_settings()
    if settings.new_relic_events_url and settings.new_relic_insert_key:
        return str(settings.new_relic_events_url), settings.new_relic_insert_key

    if settings.new_relic_account_id and settings.new_relic_insert_key:
        url = (
            "https://insights-collector.newrelic.com"
            f"/v1/accounts/{settings.new_relic_account_id}/events"
        )
        return url, settings.new_relic_insert_key

    return None, None


def emit_new_relic_event(event_type: str, attributes: Mapping[str, Any] | None = None) -> None:
    """
    Best-effort, non-blocking New Relic custom event emitter.

    No-op unless New Relic env vars are configured.
    """
    url, insert_key = _resolve_events_url()
    if not url or not insert_key:
        return

    payload: dict[str, Any] = {"eventType": event_type}
    if attributes:
        # Avoid overwriting eventType accidentally.
        for k, v in attributes.items():
            if k != "eventType":
                payload[k] = v

    headers = {"X-Insert-Key": insert_key, "Content-Type": "application/json"}

    def _send() -> None:
        try:
            with httpx.Client(timeout=2.0) as client:
                # New Relic expects an array of event objects.
                client.post(url, headers=headers, json=[payload])
        except Exception:
            # Telemetry should never break the API flow.
            pass

    threading.Thread(target=_send, name="newrelic-events", daemon=True).start()

