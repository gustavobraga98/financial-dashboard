from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from .base import Base

class Bank(Base):
    __tablename__ = "banks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)

    accounts = relationship("Account", back_populates="bank")
