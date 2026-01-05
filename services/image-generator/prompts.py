"""
Shared prompt defaults for the image-generator service.

Centralizing these prevents drift across API/worker/generator entrypoints.
"""

# Default negative prompt used across most entrypoints.
DEFAULT_NEGATIVE_PROMPT = "blurry, low quality, distorted, watermark, text, patreon logo"

# Slightly stricter default used by the "generate_images_for_run" path.
DEFAULT_NEGATIVE_PROMPT_FOR_RUN = (
    "blurry, low quality, distorted, watermark, text, speech bubble, six fingers, patreon logo"
)

