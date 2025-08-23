"""
Pydantic schemas used for serialising and validating API responses.

The `PlayAuthResponse` model now includes an optional `signed_url` field
which will contain a time‑limited, HMAC‑signed playback URL pointing to the
Audiobookshelf server.  When a caller is not authorised to play a book the
`signed_url` will be omitted (or set to ``None``) but the rest of the
payload still explains the reason and starting position.
"""

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
        orm_mode = True

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
    """

    can_play: bool
    reason: str
    start_position: float
    signed_url: Optional[str] = None
