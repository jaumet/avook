from sqlmodel import SQLModel, Field
from uuid import UUID, uuid4
from datetime import datetime, timezone

class ListeningProgress(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id")
    qr: str = Field(index=True)
    position: float = Field(nullable=False)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
