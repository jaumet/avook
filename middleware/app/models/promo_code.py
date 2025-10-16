from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlmodel import Field, SQLModel


class PromoCode(SQLModel, table=True):
    """Promo codes that can mint new audiobook entitlements."""

    __tablename__ = "promo_code"

    code: str = Field(primary_key=True)
    title_id: int = Field(foreign_key="title.id")
    label: str
    kind: str = Field(default="promo")
    campaign: Optional[str] = None
    notes: Optional[str] = None
    max_uses: Optional[int] = None
    usage_count: int = Field(default=0, nullable=False)
    expires_at: Optional[datetime] = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), nullable=False
    )


class PromoRedemption(SQLModel, table=True):
    """Audit log for promo-code redemptions."""

    __tablename__ = "promo_redemption"

    id: Optional[int] = Field(default=None, primary_key=True)
    promo_code_code: str = Field(foreign_key="promo_code.code", index=True)
    qr: str = Field(foreign_key="card.qr")
    user_id: UUID = Field(foreign_key="user.id")
    redeemed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), nullable=False
    )
    device_id: Optional[str] = None
    source: Optional[str] = None
