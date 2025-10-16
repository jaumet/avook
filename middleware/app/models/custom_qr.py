from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class CustomQr(SQLModel, table=True):
    """Marketing QR codes with campaign metadata."""

    __tablename__ = "custom_qr"

    slug: str = Field(primary_key=True)
    target_url: str
    title_id: Optional[int] = Field(default=None, foreign_key="title.id")
    label: Optional[str] = None
    campaign: Optional[str] = None
    notes: Optional[str] = None
    scan_count: int = Field(default=0, nullable=False)
    last_scanned_at: Optional[datetime] = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), nullable=False
    )


class QrScanEvent(SQLModel, table=True):
    """Individual scan event records for a custom QR."""

    __tablename__ = "qr_scan_event"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(foreign_key="custom_qr.slug", index=True)
    scanned_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), nullable=False
    )
    source: Optional[str] = None
    user_agent: Optional[str] = None
    ip: Optional[str] = None
