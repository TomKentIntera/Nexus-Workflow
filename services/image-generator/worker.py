"""
Worker that leases QUEUED runs from the API and processes them.
"""

import os
import time
import sys
import traceback
import json
import signal
import threading
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

import requests

from generator import HeartsyncModel
from prompts import DEFAULT_NEGATIVE_PROMPT


def _extract_parameters(parameter_blob: Any | None) -> dict[str, Any]:
    if isinstance(parameter_blob, dict):
        return parameter_blob
    if isinstance(parameter_blob, str):
        try:
            parsed = json.loads(parameter_blob)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _api_base_url() -> str:
    return (os.environ.get("WF_API_BASE_URL") or os.environ.get("API_BASE_URL") or "http://api:8000").rstrip("/")


def _machine_id() -> str:
    """
    Stable machine/node id.

    Priority:
    - WF_MACHINE_ID / MACHINE_ID env vars (explicit)
    - persisted file under /app/hf_cache/machine_id (docker volume)
    - generated uuid4 on first run
    """
    explicit = (os.environ.get("WF_MACHINE_ID") or os.environ.get("MACHINE_ID") or "").strip()
    if explicit:
        return explicit

    base_dir = os.environ.get("HF_HOME", "/app/hf_cache")
    os.makedirs(base_dir, exist_ok=True)
    path = os.path.join(base_dir, "machine_id")
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                v = (f.read() or "").strip()
                if v:
                    return v
    except Exception:
        pass

    v = str(uuid4())
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(v)
    except Exception:
        pass
    return v


def _lease_next_run(api_base: str) -> Optional[dict[str, Any]]:
    try:
        resp = requests.post(f"{api_base}/runs/lease", timeout=10)
    except Exception as exc:
        print(f"⚠️  Warning: Failed to reach API ({api_base}): {exc}")
        return None

    if resp.status_code == 204:
        return None
    if not resp.ok:
        print(f"⚠️  Warning: Lease request failed ({resp.status_code}): {resp.text[:300]}")
        return None
    try:
        data = resp.json()
        if isinstance(data, dict) and data.get("id"):
            return data
    except Exception:
        pass
    print("⚠️  Warning: Lease response was not valid JSON")
    return None


def _parse_dt(value: str) -> Optional[datetime]:
    """
    Parse API timestamps (typically ISO8601) into an aware UTC datetime.
    """
    v = (value or "").strip()
    if not v:
        return None
    # Common FastAPI/json formats include "...Z" or explicit offsets.
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(v)
    except Exception:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _get_queued_count(api_base: str) -> Optional[int]:
    """
    Returns the number of queued runs according to the API.
    """
    try:
        resp = requests.get(f"{api_base}/runs", timeout=10)
        if not resp.ok:
            return None
        data = resp.json()
        if isinstance(data, dict):
            qc = data.get("queued_count")
            if isinstance(qc, int):
                return qc
            if isinstance(qc, str) and qc.isdigit():
                return int(qc)
    except Exception:
        return None
    return None


def _get_latest_image_created_at(api_base: str) -> Optional[datetime]:
    """
    Returns created_at of the most recently created RunImage (any status).
    """
    try:
        resp = requests.get(f"{api_base}/runs/images", params={"limit": 1, "offset": 0}, timeout=10)
        if not resp.ok:
            return None
        data = resp.json()
        if not isinstance(data, dict):
            return None
        images = data.get("images")
        if not isinstance(images, list) or not images:
            return None
        first = images[0]
        if not isinstance(first, dict):
            return None
        created_at = first.get("created_at")
        if isinstance(created_at, str):
            return _parse_dt(created_at)
    except Exception:
        return None
    return None


def _start_watchdog(
    *,
    api_base: str,
    last_progress_utc: "dict[str, datetime]",
) -> None:
    """
    Watchdog: if there are queued runs and no image has been generated recently,
    terminate the process so Docker can restart the container (restart: unless-stopped).
    """
    enabled = (os.environ.get("WF_WATCHDOG_ENABLED", "true").strip().lower() in {"1", "true", "yes", "y", "on"})
    if not enabled:
        print("🧯 Watchdog disabled (WF_WATCHDOG_ENABLED=false)")
        return

    interval = int(os.environ.get("WF_WATCHDOG_INTERVAL_SECONDS", "60"))
    stall_seconds = int(os.environ.get("WF_WATCHDOG_STALL_SECONDS", str(30 * 60)))
    min_uptime_seconds = int(os.environ.get("WF_WATCHDOG_MIN_UPTIME_SECONDS", "600"))
    restart_signal = os.environ.get("WF_WATCHDOG_RESTART_SIGNAL", "SIGTERM").strip().upper() or "SIGTERM"

    sig = signal.SIGTERM
    if restart_signal == "SIGKILL":
        sig = signal.SIGKILL
    elif restart_signal == "SIGINT":
        sig = signal.SIGINT

    started = datetime.now(timezone.utc)

    def _loop() -> None:
        while True:
            try:
                # Don't restart during early startup (model load, first job warmup, etc.).
                now = datetime.now(timezone.utc)
                if (now - started).total_seconds() < max(min_uptime_seconds, 0):
                    time.sleep(max(interval, 5))
                    continue

                queued = _get_queued_count(api_base)
                if queued is None or queued <= 0:
                    time.sleep(max(interval, 5))
                    continue

                latest_api_image = _get_latest_image_created_at(api_base)
                last_progress = last_progress_utc.get("value")
                last_seen = max([d for d in [latest_api_image, last_progress] if d is not None], default=None)
                if last_seen is None:
                    # No visibility into progress; don't flap-restart on uncertainty.
                    time.sleep(max(interval, 5))
                    continue

                stalled_for = (now - last_seen).total_seconds()
                if stalled_for > stall_seconds:
                    print(
                        f"🧯 Watchdog: queued runs={queued} but no image generated in {int(stalled_for)}s "
                        f"(threshold={stall_seconds}s). Restarting process."
                    )
                    # Ask PID 1 to exit; docker will restart container.
                    os.kill(os.getpid(), sig)
                    # If the signal is ignored for some reason, hard-exit shortly after.
                    time.sleep(5)
                    os._exit(1)
            except Exception as exc:
                # Never let watchdog crash the worker.
                print(f"🧯 Watchdog warning: {exc}")
            time.sleep(max(interval, 5))

    t = threading.Thread(target=_loop, name="watchdog", daemon=True)
    t.start()
    print(
        f"🧯 Watchdog enabled: interval={interval}s stall_threshold={stall_seconds}s min_uptime={min_uptime_seconds}s"
    )


def _upload_image(api_base: str, run_id: str, ordinal: int, image_path: str) -> bool:
    try:
        machine_id = _machine_id()
        with open(image_path, "rb") as f:
            files = {"file": (os.path.basename(image_path), f, "image/png")}
            resp = requests.post(
                f"{api_base}/runs/{run_id}/images/upload",
                params={"ordinal": ordinal},
                files=files,
                headers={"X-Machine-Id": machine_id},
                timeout=60,
            )
        if not resp.ok:
            print(f"⚠️  Warning: Upload failed ({resp.status_code}): {resp.text[:300]}")
            return False
        return True
    except Exception as exc:
        print(f"⚠️  Warning: Upload exception for ordinal {ordinal}: {exc}")
        return False


def _set_run_status(api_base: str, run_id: str, status_value: str) -> None:
    try:
        requests.post(f"{api_base}/runs/{run_id}/status", json={"status": status_value}, timeout=10)
    except Exception:
        pass


def process_queued_runs() -> None:
    """Poll the API for available runs and process them."""
    poll_interval = int(os.environ.get("WORKER_POLL_INTERVAL", "5"))  # seconds
    model_id = os.environ.get("MODEL_ID", "Heartsync/NSFW-Uncensored")
    api_base = _api_base_url()
    machine_id = _machine_id()
    last_progress_utc: dict[str, datetime] = {"value": datetime.now(timezone.utc)}
    
    print("🚀 Image Generation Worker started")
    print(f"   Polling every {poll_interval} seconds")
    print(f"   Leasing runs from API: {api_base}")
    print(f"   Machine ID: {machine_id}")
    print()
    
    # Load model once at startup
    print("🔄 Initializing model (this may take a while on first run)...")
    model = HeartsyncModel(model_id=model_id)
    model.load_model()
    print("✅ Model loaded and ready!")
    print()

    # Start watchdog after model is ready (avoid restarting during slow first-time downloads).
    _start_watchdog(api_base=api_base, last_progress_utc=last_progress_utc)
    
    while True:
        try:
            leased = _lease_next_run(api_base)
            if not leased:
                time.sleep(poll_interval)
                continue

            run_id = leased["id"]
            prompt = (leased.get("prompt") or "").strip()
            parameters = _extract_parameters(leased.get("parameter_blob"))
            requested = int(leased.get("image_count") or parameters.get("image_count") or 1)
            generated = int(leased.get("generated_images") or 0)
            remaining = leased.get("remaining_images")
            num_images = int(remaining if remaining is not None else max(requested - generated, 0))

            width = int(parameters.get("width", 1024))
            height = int(parameters.get("height", 1024))
            negative_prompt = parameters.get(
                "negative_prompt", DEFAULT_NEGATIVE_PROMPT
            )
            num_inference_steps = int(parameters.get("steps", 28))
            guidance_scale = float(parameters.get("guidance", 7.5))
            seed = parameters.get("seed")
            if seed is not None:
                seed = int(seed)
            saturation = float(parameters.get("saturation", 1.2))
            contrast = float(parameters.get("contrast", 1.1))
            watermark_width = int(parameters.get("watermark_width", 300))

            print(f"📋 Leased run: {run_id}")
            print(f"   Prompt: {prompt[:100]}...")
            print(f"   Progress: {generated}/{requested} (remaining: {num_images})")
            print(f"   Generating {num_images} image(s) at {width}x{height}...")

            output_dir = os.environ.get("OUTPUT_DIR", "/app/generated-images")

            try:
                if num_images <= 0:
                    _set_run_status(api_base, run_id, "ready")
                    print(f"✅ Run {run_id} already complete (no remaining images)")
                    print()
                    continue

                base_seed = seed if seed is not None else None
                uploaded = 0

                for i in range(num_images):
                    ordinal = generated + i + 1  # continue ordinals after already-uploaded images
                    current_seed = base_seed + i if base_seed is not None else None
                    image, actual_seed = model.generate_image(
                        prompt=prompt,
                        negative_prompt=negative_prompt,
                        num_inference_steps=num_inference_steps,
                        guidance_scale=guidance_scale,
                        width=width,
                        height=height,
                        seed=current_seed,
                        saturation_boost=saturation,
                        contrast_boost=contrast,
                        watermark_width=watermark_width,
                    )

                    save_result = model.save_image_with_metadata(
                        image=image,
                        prompt=prompt,
                        negative_prompt=negative_prompt,
                        num_inference_steps=num_inference_steps,
                        guidance_scale=guidance_scale,
                        width=width,
                        height=height,
                        seed=actual_seed,
                        saturation_boost=saturation,
                        contrast_boost=contrast,
                        run_id=run_id,
                        output_dir=output_dir,
                        minio_client=None,
                        minio_bucket=None,
                        minio_public_base=None,
                    )

                    image_path = save_result["local_path"]
                    if _upload_image(api_base, run_id, ordinal, image_path):
                        uploaded += 1
                        last_progress_utc["value"] = datetime.now(timezone.utc)

                if uploaded == 0:
                    raise RuntimeError("No images uploaded successfully")

                _set_run_status(api_base, run_id, "ready")
                print(f"✅ Run {run_id} completed successfully ({uploaded}/{num_images} uploaded)")
                print()

            except Exception as e:
                print(f"❌ Error processing run {run_id}: {str(e)}")
                traceback.print_exc()
                _set_run_status(api_base, run_id, "error")
                print()
                    
        except Exception as e:
            print(f"❌ Error in worker loop: {str(e)}")
            traceback.print_exc()
            time.sleep(poll_interval)


if __name__ == "__main__":
    import os
    try:
        process_queued_runs()
    except KeyboardInterrupt:
        print("\n👋 Worker stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Fatal error: {str(e)}")
        traceback.print_exc()
        sys.exit(1)

