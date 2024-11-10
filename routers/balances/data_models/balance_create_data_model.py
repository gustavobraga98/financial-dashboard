from pydantic import BaseModel
from datetime import date
from typing import Optional

class BalanceCreate(BaseModel):
    date: date  # Data da transação
    value: float  # Valor do saldo

    class Config:
        orm_mode = True  # Isso permite que o Pydantic converta os modelos SQLAlchemy
