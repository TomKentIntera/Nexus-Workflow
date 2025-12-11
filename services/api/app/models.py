from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Enum as SqlEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class RunStatus(str, Enum):
    QUEUED = "queued"
    GENERATING = "generating"
    READY = "ready"
    APPROVED = "approved"
    ERROR = "error"


class RunImageStatus(str, Enum):
    GENERATED = "generated"
    APPROVED = "approved"
    REJECTED = "rejected"


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
    status: Mapped[RunImageStatus] = mapped_column(
        SqlEnum(RunImageStatus, name="run_image_status"),
        default=RunImageStatus.GENERATED,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
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