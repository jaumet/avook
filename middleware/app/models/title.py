from sqlmodel import SQLModel, Field
from typing import Optional

class Title(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    author: str
    language: str
    duration_sec: int
    cover_url: Optional[str] = None
    abs_share_code: Optional[str] = Field(default=None, unique=True)
    price_retail: float
    currency: str
    active: bool = Field(default=True)
