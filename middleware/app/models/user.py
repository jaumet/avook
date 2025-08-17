from sqlmodel import SQLModel, Field
from uuid import UUID, uuid4

class User(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(index=True, unique=True)
    password_hash: str
    name: str | None = Field(default=None)
    location: str | None = Field(default=None)
    is_admin: bool = Field(default=False)
