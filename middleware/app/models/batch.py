from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime

class Batch(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title_id: int = Field(foreign_key="title.id")
    qty: int
    printed_on: Optional[datetime] = None
    printer_vendor: Optional[str] = None
    notes: Optional[str] = None
