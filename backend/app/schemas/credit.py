from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class CreditBase(BaseModel):
    description: str
    amount: float
    type: str # 'expense' or 'income'
    category: Optional[str] = None
    date: datetime
    card_alias: str

class CreditCreate(CreditBase):
    pass

class CreditResponse(CreditBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
