from __future__ import annotations

import threading
from typing import Any, Mapping

import httpx

from ..config import get_settings


def _resolve_logs_ingest() -> tuple[str | None, str | None]:
    """
    Returns (logs_url, license_key) or (None, None) if not configured.

    Default is the US Log API. For EU, set WF_NEW_RELIC_LOGS_URL to:
    https://log-api.eu.newrelic.com/log/v1
    """
    settings = get_settings()
    if not settings.new_relic_license_key:
        return None, None
    if settings.new_relic_logs_url:
        return str(settings.new_relic_logs_url), settings.new_relic_license_key
    return "https://log-api.newrelic.com/log/v1", settings.new_relic_license_key


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
    Best-effort, non-blocking New Relic "event" emitter.

    Preferred path (license key): emits as a log record via New Relic Log API.
    Legacy path (insert key): emits as a custom event via Insights Events API.
    """
    logs_url, license_key = _resolve_logs_ingest()
    if logs_url and license_key:
        payload: dict[str, Any] = {"event_type": event_type}
        if attributes:
            for k, v in attributes.items():
                if k not in ("eventType", "event_type"):
                    payload[k] = v

        headers = {"Api-Key": license_key, "Content-Type": "application/json"}

        def _send_logs() -> None:
            try:
                with httpx.Client(timeout=2.0) as client:
                    # Log API accepts an array of log objects.
                    client.post(logs_url, headers=headers, json=[payload])
            except Exception:
                pass

        threading.Thread(target=_send_logs, name="newrelic-logs", daemon=True).start()
        return

    # Fallback: Insights custom events via insert key (legacy)
    events_url, insert_key = _resolve_events_url()
    if not events_url or not insert_key:
        return

    payload2: dict[str, Any] = {"eventType": event_type}
    if attributes:
        for k, v in attributes.items():
            if k != "eventType":
                payload2[k] = v

    headers2 = {"X-Insert-Key": insert_key, "Content-Type": "application/json"}

    def _send_events() -> None:
        try:
            with httpx.Client(timeout=2.0) as client:
                # New Relic expects an array of event objects.
                client.post(events_url, headers=headers2, json=[payload2])
        except Exception:
            # Telemetry should never break the API flow.
            pass

    threading.Thread(target=_send_events, name="newrelic-events", daemon=True).start()

