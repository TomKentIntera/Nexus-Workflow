#!/usr/bin/env python
"""
Utility entry point for triggering image generations from n8n.

This script now supports batching, optional MinIO uploads, and returns a JSON
summary describing each generated asset so the workflow can register database
records or perform follow-up actions.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from minio import Minio


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Trigger remote image generation")
    parser.add_argument(
        "--payload",
        required=True,
        help="JSON string describing the prompt or settings to send upstream",
    )
    parser.add_argument(
        "--endpoint",
        required=True,
        help="URL of the image generation API endpoint",
    )
    parser.add_argument(
        "--output",
        default="/tmp/generated.png",
        help="Where to write the generated image file when count=1",
    )
    parser.add_argument(
        "--output-dir",
        default="/tmp/generated",
        help="Directory used when generating multiple images",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="Number of images to generate",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional run identifier. Defaults to a random UUID",
    )
    parser.add_argument(
        "--minio-endpoint",
        default=os.environ.get("MINIO_ENDPOINT"),
        help="MinIO endpoint, e.g. http://minio:9000",
    )
    parser.add_argument(
        "--minio-access-key",
        default=os.environ.get("MINIO_ACCESS_KEY"),
        help="MinIO access key",
    )
    parser.add_argument(
        "--minio-secret-key",
        default=os.environ.get("MINIO_SECRET_KEY"),
        help="MinIO secret key",
    )
    parser.add_argument(
        "--minio-bucket",
        default=os.environ.get("MINIO_BUCKET", "runs"),
        help="MinIO bucket for generated assets",
    )
    parser.add_argument(
        "--minio-public-base",
        default=os.environ.get("MINIO_PUBLIC_BASE"),
        help="Optional HTTP base used when sharing public asset URLs",
    )
    parser.add_argument(
        "--minio-secure",
        action="store_true",
        help="Use HTTPS when connecting to MinIO",
    )
    return parser.parse_args()


def _get_minio_client(args: argparse.Namespace) -> Optional[Minio]:
    if not (args.minio_endpoint and args.minio_access_key and args.minio_secret_key):
        return None

    endpoint = args.minio_endpoint.replace("http://", "").replace("https://", "")
    secure = args.minio_secure or args.minio_endpoint.startswith("https://")
    return Minio(endpoint, access_key=args.minio_access_key, secret_key=args.minio_secret_key, secure=secure)


def _ensure_bucket(client: Minio, bucket: str) -> None:
    if not client.bucket_exists(bucket):  # type: ignore[arg-type]
        client.make_bucket(bucket)


def _upload_image(client: Minio, bucket: str, object_name: str, data: bytes) -> None:
    _ensure_bucket(client, bucket)
    client.put_object(bucket, object_name, BytesIO(data), length=len(data), content_type="image/png")


def _public_uri(args: argparse.Namespace, bucket: str, object_name: str, default_path: str) -> str:
    if args.minio_public_base:
        return f"{args.minio_public_base.rstrip('/')}/{bucket}/{object_name}"
    return f"s3://{bucket}/{object_name}" if args.minio_endpoint else default_path


def _generate_image(endpoint: str, payload: Dict[str, Any]) -> bytes:
    response = requests.post(endpoint, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()
    image_b64 = data.get("image_base64")
    if not image_b64:
        raise RuntimeError("Response did not include 'image_base64'")
    return base64.b64decode(image_b64)


def main() -> None:
    args = parse_args()
    payload = json.loads(args.payload)
    run_id = args.run_id or str(uuid.uuid4())
    count = max(1, args.count)

    output_path = Path(args.output)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    minio_client = _get_minio_client(args)
    summary: List[Dict[str, Any]] = []

    for ordinal in range(1, count + 1):
        image_bytes = _generate_image(args.endpoint, payload)

        if count == 1 and output_path.suffix:
            target_path = output_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            target_path = output_dir / f"{run_id}-{ordinal:02d}.png"

        target_path.write_bytes(image_bytes)
        object_name = f"runs/{run_id}/{target_path.name}"
        asset_uri = str(target_path)

        if minio_client:
            _upload_image(minio_client, args.minio_bucket, object_name, image_bytes)
            asset_uri = _public_uri(args, args.minio_bucket, object_name, asset_uri)

        summary.append(
            {
                "run_id": run_id,
                "ordinal": ordinal,
                "asset_uri": asset_uri,
                "local_path": str(target_path),
            }
        )

    print(json.dumps({"run_id": run_id, "images": summary}))


if __name__ == "__main__":
    main()
