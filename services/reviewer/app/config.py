from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    api_base_url: str = Field("http://api:8000", description="Workflow API base URL")
    default_approver: str = Field("reviewer", description="Fallback approver name")
    request_timeout: float = Field(15.0, description="HTTP timeout in seconds")

    class Config:
        env_prefix = "REVIEWER_"
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
