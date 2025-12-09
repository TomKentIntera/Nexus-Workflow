#!/usr/bin/env python
"""
Utility entry point for triggering image generations from n8n.

This script is intentionally lightweight—it simply forwards a payload to an
external API (for example, a Stable Diffusion inference endpoint) and writes
the resulting image bytes to disk. Extend it to suit your workflow.
"""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

import requests


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
        help="Where to write the generated image file",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = json.loads(args.payload)

    response = requests.post(args.endpoint, json=payload, timeout=60)
    response.raise_for_status()

    data = response.json()
    image_b64 = data.get("image_base64")
    if not image_b64:
        raise RuntimeError("Response did not include 'image_base64'")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(base64.b64decode(image_b64))
    print(f"Image written to {output_path}")


if __name__ == "__main__":
    main()
