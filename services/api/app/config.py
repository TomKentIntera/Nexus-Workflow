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
