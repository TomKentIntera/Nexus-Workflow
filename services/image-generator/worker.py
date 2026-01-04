"""
Worker that leases QUEUED runs from the API and processes them.
"""

import os
import time
import sys
import traceback
import json
from typing import Any, Optional
from uuid import uuid4

import requests

from generator import HeartsyncModel


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
                "negative_prompt", "blurry, low quality, distorted, watermark, text"
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

