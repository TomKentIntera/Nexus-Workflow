"""
Shared prompt defaults for the image-generator service.

Centralizing these prevents drift across API/worker/generator entrypoints.
"""

# Default negative prompt used across entrypoints.
#
# Note: This is intentionally "strict" since we currently overlay a Patreon logo;
# in many contexts we want to avoid generating the logo inside the image itself.
DEFAULT_NEGATIVE_PROMPT = (
    "blurry, low quality, distorted, watermark, text, speech bubble, six fingers, patreon logo"
)

# Back-compat alias (kept to avoid churn across call sites).
DEFAULT_NEGATIVE_PROMPT_FOR_RUN = DEFAULT_NEGATIVE_PROMPT

