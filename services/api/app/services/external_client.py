from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import urljoin

import httpx

from ..config import get_settings
from ..schemas import ExternalCallRequest, ExternalCallResponse


class ExternalAPIError(Exception):
    """Raised when the upstream API call cannot be completed."""


class ExternalAPIClient:
    def __init__(
        self,
        base_url: Optional[str],
        timeout: float,
        default_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.default_headers = default_headers or {}

    async def forward(self, request: ExternalCallRequest) -> ExternalCallResponse:
        url = self._build_url(request)
        headers = {**self.default_headers, **(request.headers or {})}

        async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
            try:
                response = await client.request(
                    request.method,
                    url,
                    params=request.query,
                    json=request.payload,
                )
            except httpx.HTTPError as exc:
                raise ExternalAPIError(str(exc)) from exc

        data: Any
        try:
            data = response.json()
        except ValueError:
            data = response.text

        return ExternalCallResponse(
            status_code=response.status_code,
            data=data,
            headers=dict(response.headers),
        )

    def _build_url(self, request: ExternalCallRequest) -> str:
        if request.path.startswith("http://") or request.path.startswith("https://"):
            return request.path

        base_url = request.base_url_override or self.base_url
        if not base_url:
            raise ExternalAPIError(
                "No external API base URL configured. "
                "Set WF_EXTERNAL_API_BASE or provide base_url_override."
            )

        return urljoin(str(base_url).rstrip("/") + "/", request.path.lstrip("/"))


def get_external_client() -> ExternalAPIClient:
    settings = get_settings()
    return ExternalAPIClient(
        base_url=str(settings.external_api_base) if settings.external_api_base else None,
        timeout=settings.request_timeout,
        default_headers=settings.default_headers,
    )
