from functools import lru_cache
from typing import Dict, Optional

from pydantic import AnyHttpUrl, Field, HttpUrl
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    platform_api_base: Optional[HttpUrl] = None
    request_timeout: float = 10.0
    default_headers: Dict[str, str] = Field(default_factory=dict)
    database_url: Optional[str] = None
    minio_endpoint: Optional[AnyHttpUrl] = None
    minio_public_endpoint: Optional[AnyHttpUrl] = None
    minio_bucket: str = "runs"
    minio_access_key: Optional[str] = None
    minio_secret_key: Optional[str] = None
    cors_allow_origins: str = "*"
    n8n_link_submission_webhook: Optional[HttpUrl] = None

    # Posting schedule settings
    posting_window_start: str = Field(
        "12:00:00", description="Posting window start (HH:MM or HH:MM:SS)"
    )
    posting_window_end: str = Field(
        "21:00:00", description="Posting window end (HH:MM or HH:MM:SS)"
    )
    max_posts_per_day: int = Field(5, ge=1, description="Maximum posts per day")
    schedule_delay_min: int = Field(
        30, ge=0, description="Minimum minutes after last post"
    )
    schedule_delay_max: int = Field(
        90, ge=0, description="Maximum minutes after last post"
    )

    # New Relic telemetry (optional)
    #
    # Preferred (license key): we emit these "events" as New Relic Logs, using the Log API.
    # - new_relic_license_key: New Relic account license key
    # - new_relic_logs_url: optional override (e.g. EU region endpoint)
    new_relic_license_key: Optional[str] = None
    new_relic_logs_url: Optional[AnyHttpUrl] = None

    # Legacy (insert key) support kept for compatibility. If present and license key is not set,
    # we will send to the Insights Events endpoint.
    new_relic_events_url: Optional[AnyHttpUrl] = None
    new_relic_account_id: Optional[str] = None
    new_relic_insert_key: Optional[str] = None

    # Tag filtering (used by n8n workflows)
    # - WF_BANNED_TAGS: comma/newline-separated or JSON list (e.g. '["English text","logo"]')
    # - WF_BANNED_TAGS_FILE: optional path to a file containing tags (one per line or comma-separated)
    banned_tags: str = ""
    banned_tags_file: Optional[str] = None

    # WD1.4 (SmilingWolf wd-v1-4-convnext-tagger) autotagging settings
    wd14_repo_id: str = "SmilingWolf/wd-v1-4-convnext-tagger"
    wd14_model_filename: str = "model.onnx"
    wd14_tags_filename: str = "selected_tags.csv"
    wd14_cache_dir: str = "/tmp/wd14_cache"
    wd14_general_threshold: float = 0.35
    wd14_character_threshold: float = 0.85

    # New Relic settings
    new_relic_license_key: Optional[str] = None
    new_relic_app_name: str = "Nexus Workflow API"
    new_relic_enabled: bool = True

    class Config:
        env_prefix = "WF_"
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
