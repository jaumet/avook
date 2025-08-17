from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime, timezone

class Claim(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    qr: str = Field(index=True, unique=True)
    claimed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    owner_email: str
    borrower_email: Optional[str] = None
    lent_at: Optional[datetime] = None
    returned_at: Optional[datetime] = None
    status: Optional[int] = Field(default=1)
