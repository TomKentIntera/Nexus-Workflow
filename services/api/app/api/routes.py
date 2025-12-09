from fastapi import APIRouter, HTTPException

from ..schemas import ExternalCallRequest, ExternalCallResponse
from ..services.external_client import ExternalAPIError, get_external_client

router = APIRouter(prefix="/external", tags=["external"])


@router.post("/call", response_model=ExternalCallResponse)
async def external_call(payload: ExternalCallRequest) -> ExternalCallResponse:
    client = get_external_client()
    try:
        return await client.forward(payload)
    except ExternalAPIError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
