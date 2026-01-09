from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Enum as SqlEnum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class RunStatus(str, Enum):
    QUEUED = "queued"
    GENERATING = "generating"
    READY = "ready"
    APPROVED = "approved"
    ERROR = "error"
    POSTED = "posted"


class RunImageStatus(str, Enum):
    GENERATED = "GENERATED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    POSTED = "POSTED"


class WebhookStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workflow_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    parameter_blob: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    status: Mapped[RunStatus] = mapped_column(
        SqlEnum(RunStatus, name="run_status"), default=RunStatus.QUEUED, nullable=False
    )
    leased_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    images: Mapped[list["RunImage"]] = relationship(
        "RunImage", back_populates="run", cascade="all, delete-orphan", lazy="selectin"
    )


class RunImage(Base):
    __tablename__ = "run_images"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    asset_uri: Mapped[str] = mapped_column(Text, nullable=False)
    thumb_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_by_machine_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # When an image is approved for posting, the API assigns a scheduled time so approvals
    # can be spread out over time (e.g., last scheduled + 30 minutes).
    scheduled_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[RunImageStatus] = mapped_column(
        SqlEnum(RunImageStatus, name="run_image_status"),
        default=RunImageStatus.GENERATED,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    fanvue_uuid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    r34_uuid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    run: Mapped[Run] = relationship("Run", back_populates="images")
    approvals: Mapped[list["RunImageApproval"]] = relationship(
        "RunImageApproval", back_populates="run_image", cascade="all, delete-orphan"
    )


class RunImageApproval(Base):
    __tablename__ = "run_image_approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_image_id: Mapped[str] = mapped_column(
        ForeignKey("run_images.id", ondelete="CASCADE"), nullable=False
    )
    approved_by: Mapped[str] = mapped_column(String(128), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    webhook_status: Mapped[WebhookStatus] = mapped_column(
        SqlEnum(WebhookStatus, name="webhook_status"),
        default=WebhookStatus.PENDING,
        nullable=False,
    )
    webhook_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    webhook_last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    run_image: Mapped[RunImage] = relationship("RunImage", back_populates="approvals")


class LinkSubmission(Base):
    __tablename__ = "link_submissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    url: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    webhook_status: Mapped[WebhookStatus] = mapped_column(
        SqlEnum(WebhookStatus, name="link_webhook_status"),
        default=WebhookStatus.PENDING,
        nullable=False,
    )
    webhook_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    webhook_last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class BannedTag(Base):
    __tablename__ = "banned_tags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tag: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


class AllowedSearchTag(Base):
    """
    Allowlisted tags for "post search" / generation context.

    Typically:
    - type="series", tag="<series name>"
    - type="character", tag="<character name>"
    """

    __tablename__ = "allowed_search_tags"
    __table_args__ = (
        UniqueConstraint("type", "tag", name="uq_allowed_search_tags_type_tag"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    tag: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )