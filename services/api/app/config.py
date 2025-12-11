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

    class Config:
        env_prefix = "WF_"
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
