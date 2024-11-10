from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum as SQLAEnum
from sqlalchemy.orm import relationship
from postgres.data_models.general_base import Base
from enum import Enum

class Balance(Base):
    __tablename__ = 'Balance'

    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime, nullable=False)
    value = Column(Float, nullable=False)
