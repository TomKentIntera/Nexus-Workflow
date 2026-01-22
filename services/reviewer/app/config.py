from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    api_base_url: str = Field("http://api:8000", description="Workflow API base URL")
    rule34_base_url: str = Field("https://rule34.nexus", description="Rule34 Nexus base URL")
    default_approver: str = Field("reviewer", description="Fallback approver name")
    request_timeout: float = Field(15.0, description="HTTP timeout in seconds")
    images_per_day: Optional[int] = Field(
        None, description="Images to post per day (scheduler config)"
    )
    posting_window_start: Optional[str] = Field(
        None, description="Posting window start (HH:MM or HH:MM:SS)"
    )
    posting_window_end: Optional[str] = Field(
        None, description="Posting window end (HH:MM or HH:MM:SS)"
    )

    class Config:
        env_prefix = "REVIEWER_"
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
