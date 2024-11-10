from pydantic import BaseModel
from typing import Optional
from enum import Enum
import datetime

# Recria a Enum do SQLAlchemy para uso no Pydantic
class TypeType(str, Enum):
    INCOME = "income"
    OUTCOME = "outcome"

class TransactionModel(BaseModel):
    type: TypeType
    value: float
    description: Optional[str] = ""
    category: Optional[str] = "Desconhecida"
    date: Optional[datetime.date] = None  # Permite que a data seja opcional e aceita uma data personalizada


class BalanceRead(TransactionModel):
    id: int  # Adiciona o campo `id` para o modelo de leitura

    class Config:
        from_attributes = True  # Permite que o Pydantic converta os dados de um modelo SQLAlchemy
