"""
Database connection and models for image-generator service.
"""

from contextlib import contextmanager
import os
from sqlalchemy import create_engine, String, Text, Integer, DateTime, Enum as SqlEnum, ForeignKey, JSON
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker, Mapped, mapped_column, relationship
from sqlalchemy.dialects.mysql import JSON as MySQLJSON
from datetime import datetime
from enum import Enum
from typing import Optional, Any
from uuid import uuid4


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""


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


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workflow_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    parameter_blob: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[RunStatus] = mapped_column(
        SqlEnum(RunStatus, name="run_status"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    images: Mapped[list["RunImage"]] = relationship("RunImage", back_populates="run", lazy="selectin")


class RunImage(Base):
    __tablename__ = "run_images"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    asset_uri: Mapped[str] = mapped_column(Text, nullable=False)
    thumb_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[RunImageStatus] = mapped_column(
        SqlEnum(RunImageStatus, name="run_image_status"),
        default=RunImageStatus.GENERATED,
        nullable=False,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    run: Mapped[Run] = relationship("Run", back_populates="images")


# Database connection
def get_database_url() -> str:
    """Get database URL from environment variables."""
    db_user = os.environ.get("DB_USER", "workflow")
    db_password = os.environ.get("DB_PASSWORD", "workflow")
    db_host = os.environ.get("DB_HOST", "mysql")
    db_port = os.environ.get("DB_PORT", "3306")
    db_name = os.environ.get("DB_NAME", "workflow")
    
    return f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"


database_url = get_database_url()
engine = create_engine(
    database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@contextmanager
def get_db_session():
    """Get a database session with automatic cleanup."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

