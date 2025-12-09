from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, MutableMapping, Optional
from urllib.parse import urljoin

import httpx

from ..config import get_settings


@dataclass
class PlatformResponse:
    status_code: int
    data: Any
    headers: Dict[str, str]


class PlatformAPIError(Exception):
    """Raised when the platform API cannot fulfill the request."""


class PlatformAPIClient:
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.platform_api_base:
            raise PlatformAPIError(
                "WF_PLATFORM_API_BASE is not configured in the API service .env"
            )
        self.base_url = str(settings.platform_api_base).rstrip("/")
        self.timeout = settings.request_timeout
        self.default_headers = settings.default_headers

    async def request(
        self,
        method: str,
        path: str,
        *,
        query: Optional[Mapping[str, Any]] = None,
        payload: Optional[Any] = None,
        headers: Optional[MutableMapping[str, str]] = None,
    ) -> PlatformResponse:
        url = self._build_url(path)
        merged_headers = {**self.default_headers, **(headers or {})}

        async with httpx.AsyncClient(
            timeout=self.timeout, headers=merged_headers
        ) as client:
            try:
                response = await client.request(
                    method,
                    url,
                    params=query,
                    json=payload,
                )
            except httpx.HTTPError as exc:
                raise PlatformAPIError(str(exc)) from exc

        try:
            data = response.json()
        except ValueError:
            data = response.text

        return PlatformResponse(
            status_code=response.status_code,
            data=data,
            headers=dict(response.headers),
        )

    def _build_url(self, path: str) -> str:
        # Allow callers to pass absolute URLs for edge cases.
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return urljoin(f"{self.base_url}/", path.lstrip("/"))


def get_platform_client() -> PlatformAPIClient:
    return PlatformAPIClient()
