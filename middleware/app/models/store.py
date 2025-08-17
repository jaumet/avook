from sqlmodel import SQLModel, Field
from typing import Optional

class Store(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    channel_type: str
    city: Optional[str] = None
    country: Optional[str] = None
    contact_email: Optional[str] = None
    external_ref: Optional[str] = None
