from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID

class Card(SQLModel, table=True):
    qr: str = Field(primary_key=True)
    title_id: int = Field(foreign_key="title.id")
    user_state: int = Field(default=0)
    owner_user_id: Optional[UUID] = Field(default=None, foreign_key="user.id")
    borrower_user_id: Optional[UUID] = Field(default=None, foreign_key="user.id")
    retail_state: str = Field(default="warehouse")
    store_id: Optional[int] = Field(default=None, foreign_key="store.id")
    batch_id: Optional[int] = Field(default=None, foreign_key="batch.id")
    claimed_at: Optional[datetime] = None
    lent_at: Optional[datetime] = None
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow, nullable=False)
    notes: Optional[str] = None
