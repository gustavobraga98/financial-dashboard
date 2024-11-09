from sqlalchemy import Column, Integer, String, Float,DateTime, Enum as SQLAEnum
from postgres.data_models.general_base import Base
from enum import Enum
from datetime import datetime, timezone

class TypeType(str, Enum):
    START = "start"
    INCOME = "income"
    OUTCOME = "outcome"

class Balance(Base):
    __tablename__ = 'Balance'

    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime, nullable=False)  # Remova o valor padrão
    type = Column(SQLAEnum(TypeType, create_constraint=True), nullable=False)
    value = Column(Float, nullable=False)
    description = Column(String, nullable=True)
    category = Column(String, nullable=True)

    
