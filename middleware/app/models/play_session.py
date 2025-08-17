from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime, timezone

class PlaySession(SQLModel, table=True):
    """Represents a playback session on a particular device.

    A session records when a signed playback URL was issued and when it
    expires.  The default for ``issued_at`` uses UTC to avoid timezone
    confusion.
    """

    id: int | None = Field(default=None, primary_key=True)
    qr: str = Field(index=True)
    device_id: str | None = None
    issued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
