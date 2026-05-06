from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class AccountBase(BaseModel):
    name: str
    initial_balance: float = 0.0
    initial_balance_date: Optional[datetime] = None

class AccountCreate(AccountBase):
    pass

class AccountResponse(AccountBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
