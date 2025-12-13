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
    n8n_approval_webhook: Optional[AnyHttpUrl] = None

    # WD1.4 (SmilingWolf wd-v1-4-convnext-tagger) autotagging settings
    wd14_repo_id: str = "SmilingWolf/wd-v1-4-convnext-tagger"
    wd14_model_filename: str = "model.onnx"
    wd14_tags_filename: str = "selected_tags.csv"
    wd14_cache_dir: str = "/tmp/wd14_cache"
    wd14_general_threshold: float = 0.35
    wd14_character_threshold: float = 0.85

    class Config:
        env_prefix = "WF_"
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
