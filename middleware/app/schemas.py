"""
Pydantic schemas used for serialising and validating API responses.

The `PlayAuthResponse` model now includes an optional `signed_url` field
which will contain a time‑limited, HMAC‑signed playback URL pointing to the
Audiobookshelf server.  When a caller is not authorised to play a book the
`signed_url` will be omitted (or set to ``None``) but the rest of the
payload still explains the reason and starting position.
"""

from datetime import date, datetime
from pydantic import BaseModel
from typing import Optional
from uuid import UUID


class UserBase(BaseModel):
    email: str
    name: str
    location: str

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: UUID
    is_admin: bool

    class Config:
        from_attributes = True


class DashboardTotals(BaseModel):
    users: int
    titles: int
    cards: int
    claimed_cards: int
    active_loans: int


class DashboardDailyStat(BaseModel):
    date: date
    count: int


class AdminDashboard(BaseModel):
    generated_at: datetime
    totals: DashboardTotals
    activations_last_30_days: int
    loans_last_30_days: int
    activations_trend: list[DashboardDailyStat]
    loans_trend: list[DashboardDailyStat]

class UserUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    password: Optional[str] = None
    password_confirm: Optional[str] = None

class UserUpdateAdmin(BaseModel):
    email: Optional[str] = None
    name: Optional[str] = None
    location: Optional[str] = None
    is_admin: Optional[bool] = None

class Token(BaseModel):
    access_token: str
    token_type: str

class PlayAuthResponse(BaseModel):
    """Response for the play‑auth endpoint.

    Attributes:
        can_play: whether the authenticated user may start playback.
        reason: textual explanation of why playback is allowed or denied.
        start_position: the progress (in seconds or fraction) where
            playback should begin.
        signed_url: a signed Audiobookshelf playback URL, only included
            when ``can_play`` is ``True``.
        abs_stream_url: absolute Audiobookshelf stream URL returned by the
            upstream service once validated.
    """

    can_play: bool
    reason: str
    start_position: float
    signed_url: Optional[str] = None
    redirect_url: Optional[str] = None
    expires_in: Optional[int] = None
    abs_stream_url: Optional[str] = None


class ProxyValidationResponse(BaseModel):
    ok: bool
    qr: str
    user_id: UUID
    device_id: str
    abs_share_code: Optional[str] = None
    stream_url: Optional[str] = None
    expires_at: int
