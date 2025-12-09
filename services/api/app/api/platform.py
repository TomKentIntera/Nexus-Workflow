from typing import Any, Dict

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from ..clients.platform import PlatformAPIError, get_platform_client

router = APIRouter(prefix="/platform", tags=["platform"])


def _format_response(result_data: Any, status_code: int) -> Response:
    if isinstance(result_data, (dict, list)):
        return JSONResponse(status_code=status_code, content=result_data)
    return PlainTextResponse(status_code=status_code, content=str(result_data))


@router.get("/{path:path}")
async def proxy_platform_get(path: str, request: Request) -> Response:
    client = get_platform_client()
    try:
        result = await client.request(
            "GET", path, query=dict(request.query_params)
        )
    except PlatformAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return _format_response(result.data, result.status_code)


@router.post("/{path:path}")
async def proxy_platform_post(
    path: str,
    request: Request,
    payload: Dict[str, Any] | None = Body(default=None),
) -> Response:
    client = get_platform_client()
    try:
        result = await client.request(
            "POST",
            path,
            query=dict(request.query_params),
            payload=payload,
        )
    except PlatformAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return _format_response(result.data, result.status_code)
