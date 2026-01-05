from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, List, Optional

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from .models import RunImageStatus, RunStatus


class RunImageCreate(BaseModel):
    ordinal: int
    asset_uri: str
    thumb_uri: Optional[str] = None
    generated_by_machine_id: Optional[str] = None
    notes: Optional[str] = None


class RunImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    ordinal: int
    asset_uri: str
    thumb_uri: Optional[str] = None
    generated_by_machine_id: Optional[str] = None
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
    leased_until: Optional[datetime] = None
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


class RunLeaseResponse(BaseModel):
    """Response returned to an image-generator when leasing a run."""

    id: str
    workflow_id: Optional[str] = None
    prompt: str
    parameter_blob: Optional[Any] = Field(default=None, description="Opaque workflow payload")
    image_count: int = Field(default=1, ge=1, description="Total number of images requested for this run")
    generated_images: int = Field(default=0, ge=0, description="Number of images already uploaded for this run")
    remaining_images: int = Field(default=1, ge=0, description="Number of images remaining to generate/upload")
    leased_until: Optional[datetime] = None


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


class ImagesPerHourStats(BaseModel):
    hours: List[str] = []
    machines: List[str] = []
    data: List[dict] = []


class ReviewerSummary(BaseModel):
    approved_images: int = 0
    posted_images: int = 0
    runs_need_review: int = 0
    images_generated_last_hour: int = 0


class ImagesLastHourByMachine(BaseModel):
    data: List[dict] = []
    total: int = 0


class RunImageListItem(BaseModel):
    id: str
    run_id: str
    ordinal: int
    asset_uri: str
    thumb_uri: Optional[str] = None
    generated_by_machine_id: Optional[str] = None
    status: RunImageStatus
    notes: Optional[str] = None
    created_at: datetime
    run_created_at: Optional[datetime] = None
    prompt: Optional[str] = None
    scheduled_time: Optional[datetime] = None


class RunImageList(BaseModel):
    images: List[RunImageListItem] = []
    total: int = 0
    limit: int = 0
    offset: int = 0


class BannedTagsUpsert(BaseModel):
    """
    Add banned tags (idempotent).
    """

    tags: List[str] = Field(default_factory=list, description="Tags to add to the banned list")


class AllowedSearchTagType(str, Enum):
    SERIES = "series"
    CHARACTER = "character"


class AllowedSearchTagItem(BaseModel):
    """
    A single allowed search tag entry.
    """

    type: AllowedSearchTagType = Field(
        ...,
        description='Tag namespace/type (usually "series" or "character")',
    )
    tag: str = Field(..., description="The tag value, e.g. series or character name")


class AllowedSearchTagsUpsert(BaseModel):
    """
    Add allowed search tags (idempotent).
    """

    tags: List[AllowedSearchTagItem] = Field(
        default_factory=list, description="Allowed search tags to add"
    )


class AllowedSearchTagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: str
    tag: str