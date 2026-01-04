from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from .models import RunImageStatus, RunStatus


class RunImageCreate(BaseModel):
    ordinal: int
    asset_uri: str
    thumb_uri: Optional[str] = None
    notes: Optional[str] = None


class RunImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    ordinal: int
    asset_uri: str
    thumb_uri: Optional[str] = None
    status: RunImageStatus
    notes: Optional[str] = None
    created_at: datetime


class RunBase(BaseModel):
    workflow_id: Optional[str] = None
    prompt: str
    parameter_blob: Optional[Any] = Field(default=None, description="Opaque workflow payload")


class RunCreate(RunBase):
    status: RunStatus = RunStatus.READY
    images: List[RunImageCreate] = []


class RunUpdateStatus(BaseModel):
    status: RunStatus


class RunRead(RunBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: RunStatus
    created_at: datetime
    updated_at: datetime
    images: List[RunImageRead] = []


class RunList(BaseModel):
    runs: List[RunRead]
    queued_count: int = 0
    images_generated_last_hour: int = 0


class RunImageApprovalRequest(BaseModel):
    approved_by: str
    notes: Optional[str] = None


class RunImageApprovalResponse(BaseModel):
    approval_id: str
    image_id: str
    webhook_status: str


class LinkSubmissionCreate(BaseModel):
    url: AnyHttpUrl
    source_url: Optional[AnyHttpUrl] = None


class LinkSubmissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    url: str
    source_url: Optional[str] = None
    created_at: datetime
    webhook_status: str
    webhook_attempts: int
    webhook_last_error: Optional[str] = None


class LinkSubmissionList(BaseModel):
    submissions: List[LinkSubmissionRead]