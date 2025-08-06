from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlmodel import Relationship
from sqlmodel import Field



class User(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(index=True, unique=True)
    password_hash: str

class Claim(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    qr: str = Field(index=True, unique=True)
    claimed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    owner_email: str
    borrower_email: Optional[str] = None
    lent_at: Optional[datetime] = None
    returned_at: Optional[datetime] = None
    status: Optional[int] = Field(default=1)  # 🔁 camp afegit correctament


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


class ListeningProgress(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id")
    qr: str = Field(index=True)
    position: float = Field(nullable=False)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

