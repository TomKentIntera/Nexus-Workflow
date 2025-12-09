from functools import lru_cache
from typing import Dict, Optional

from pydantic import BaseSettings, Field, HttpUrl


class Settings(BaseSettings):
    platform_api_base: Optional[HttpUrl] = None
    request_timeout: float = 10.0
    default_headers: Dict[str, str] = Field(default_factory=dict)

    class Config:
        env_prefix = "WF_"
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
