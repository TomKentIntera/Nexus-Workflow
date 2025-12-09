from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, HttpUrl


class ExternalCallRequest(BaseModel):
    path: str
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    query: Optional[Dict[str, Any]] = None
    payload: Optional[Any] = None
    headers: Optional[Dict[str, str]] = None
    base_url_override: Optional[HttpUrl] = None


class ExternalCallResponse(BaseModel):
    status_code: int
    data: Any | None = None
    headers: Dict[str, str]
