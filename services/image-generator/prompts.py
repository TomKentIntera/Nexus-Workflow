"""
Shared prompt defaults for the image-generator service.

Centralizing these prevents drift across API/worker/generator entrypoints.
"""

# Default negative prompt used across entrypoints.
#
# Note: The base negative prompt words are now stored in the database and retrieved
# via the lease endpoint. This default is kept for backward compatibility and as a
# fallback, but should typically be empty or minimal since words come from the DB.
DEFAULT_NEGATIVE_PROMPT = ""

# Back-compat alias (kept to avoid churn across call sites).
DEFAULT_NEGATIVE_PROMPT_FOR_RUN = DEFAULT_NEGATIVE_PROMPT

