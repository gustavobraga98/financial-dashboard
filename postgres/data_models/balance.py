from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum as SQLAEnum
from sqlalchemy.orm import relationship
from postgres.data_models.general_base import Base
from enum import Enum

class TypeType(str, Enum):
    START = "start"
    INCOME = "income"
    OUTCOME = "outcome"

class Balance(Base):
    __tablename__ = 'Balance'

    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime, nullable=False)
    type = Column(SQLAEnum(TypeType, create_constraint=True), nullable=False)
    value = Column(Float, nullable=False)
    description = Column(String, nullable=True)
    category_id = Column(Integer, ForeignKey("Categories.id"), nullable=True)  # Definindo a chave estrangeira

    # Define o relacionamento com a tabela Categories
    category = relationship("Categories", back_populates="balances")
