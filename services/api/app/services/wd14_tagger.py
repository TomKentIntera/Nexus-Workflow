from __future__ import annotations

import csv
import os
import threading
from dataclasses import dataclass
from io import BytesIO

import numpy as np
import onnxruntime as ort
from huggingface_hub import hf_hub_download
from PIL import Image

from ..config import get_settings


class WD14TaggerError(RuntimeError):
    """Raised when the WD14 tagger cannot load or run."""


@dataclass(frozen=True)
class WD14Tag:
    name: str
    score: float
    category: int


_lock = threading.Lock()
_session: ort.InferenceSession | None = None
_tags: list[tuple[str, int]] | None = None  # (name, category) aligned to output indices


def _ensure_loaded() -> tuple[ort.InferenceSession, list[tuple[str, int]]]:
    global _session, _tags
    if _session is not None and _tags is not None:
        return _session, _tags

    with _lock:
        if _session is not None and _tags is not None:
            return _session, _tags

        settings = get_settings()
        os.makedirs(settings.wd14_cache_dir, exist_ok=True)

        try:
            model_path = hf_hub_download(
                repo_id=settings.wd14_repo_id,
                filename=settings.wd14_model_filename,
                cache_dir=settings.wd14_cache_dir,
            )
            tags_path = hf_hub_download(
                repo_id=settings.wd14_repo_id,
                filename=settings.wd14_tags_filename,
                cache_dir=settings.wd14_cache_dir,
            )
        except Exception as exc:  # pragma: no cover
            raise WD14TaggerError(f"Failed to download WD14 model assets: {exc}") from exc

        try:
            providers = ["CPUExecutionProvider"]
            _session = ort.InferenceSession(model_path, providers=providers)
        except Exception as exc:
            raise WD14TaggerError(f"Failed to load WD14 ONNX model: {exc}") from exc

        try:
            parsed: list[tuple[str, int]] = []
            with open(tags_path, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = (row.get("name") or "").strip()
                    category = int(row.get("category") or "0")
                    parsed.append((name, category))
            if not parsed:
                raise WD14TaggerError("WD14 tags file was empty or unreadable")
            _tags = parsed
        except Exception as exc:
            raise WD14TaggerError(f"Failed to load WD14 tags CSV: {exc}") from exc

        return _session, _tags


def _prepare_image(image_bytes: bytes, size: int = 448) -> np.ndarray:
    if not image_bytes or len(image_bytes) == 0:
        raise WD14TaggerError("Image bytes are empty")
    
    try:
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:
        raise WD14TaggerError(f"Unable to decode image: {exc}") from exc

    # Verify image is valid
    w, h = img.size
    if w == 0 or h == 0:
        raise WD14TaggerError(f"Invalid image dimensions: {w}x{h}")
    
    # Check if image is mostly black/empty by sampling
    sample = np.asarray(img)
    if sample.size > 0:
        # Check if image is mostly black (mean < 10) or mostly white (mean > 245)
        mean_brightness = np.mean(sample)
        std_brightness = np.std(sample)
        min_brightness = np.min(sample)
        max_brightness = np.max(sample)
        
        # Log image statistics for debugging (using print with flush for immediate visibility)
        import sys
        print(f"[WD14] Image stats - size: {w}x{h}, mean: {mean_brightness:.1f}, std: {std_brightness:.1f}, range: [{min_brightness:.1f}, {max_brightness:.1f}]", file=sys.stderr, flush=True)
        
        # Warn if image is very dark but don't fail (might be intentional)
        if mean_brightness < 20:
            print(f"[WD14] WARNING: Image is very dark (mean brightness: {mean_brightness:.1f}) - results may be inaccurate", file=sys.stderr, flush=True)
        if mean_brightness > 235:
            print(f"[WD14] WARNING: Image is very bright (mean brightness: {mean_brightness:.1f}) - results may be inaccurate", file=sys.stderr, flush=True)
        
        # Only fail if image is completely uniform (likely corrupted)
        if std_brightness < 1.0:
            raise WD14TaggerError(f"Image appears to be uniform/corrupted (mean: {mean_brightness:.1f}, std: {std_brightness:.1f})")

    # Pad to square (white background) then resize
    side = max(w, h)
    canvas = Image.new("RGB", (side, side), (255, 255, 255))
    canvas.paste(img, ((side - w) // 2, (side - h) // 2))
    canvas = canvas.resize((size, size), resample=Image.BICUBIC)

    arr = np.asarray(canvas).astype(np.float32) / 255.0
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    arr = (arr - mean) / std
    # Keep HWC format (NHWC after batch dimension is added)
    arr = np.expand_dims(arr, 0)  # NHWC: [1, height, width, channels]
    return arr


def wd14_autotag(
    image_bytes: bytes,
    *,
    general_threshold: float | None = None,
    character_threshold: float | None = None,
    include_ratings: bool = False,
) -> list[WD14Tag]:
    """
    Runs WD1.4 tagging and returns tags with scores above thresholds.

    Categories (from selected_tags.csv):
    - 9: ratings (e.g. rating:safe)
    - 4: character
    - 0: general (and other non-rating categories commonly treated as tags)
    """
    session, tags = _ensure_loaded()
    settings = get_settings()
    gen_t = settings.wd14_general_threshold if general_threshold is None else general_threshold
    char_t = (
        settings.wd14_character_threshold
        if character_threshold is None
        else character_threshold
    )

    inp = _prepare_image(image_bytes)
    input_name = session.get_inputs()[0].name

    try:
        out = session.run(None, {input_name: inp})[0]
    except Exception as exc:
        raise WD14TaggerError(f"WD14 inference failed: {exc}") from exc

    probs = np.asarray(out).reshape(-1).astype(np.float32)
    if len(probs) != len(tags):
        raise WD14TaggerError(
            f"WD14 output size mismatch: got {len(probs)} scores, expected {len(tags)}"
        )

    results: list[WD14Tag] = []
    for (name, category), score in zip(tags, probs):
        if not name:
            continue
        if category == 9 and not include_ratings:
            continue
        if category == 4:
            if float(score) < char_t:
                continue
        elif category != 9:
            if float(score) < gen_t:
                continue

        # Common formatting: underscores -> spaces
        results.append(WD14Tag(name=name.replace("_", " "), score=float(score), category=category))

    results.sort(key=lambda t: t.score, reverse=True)
    return results

