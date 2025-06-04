from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from .base import Base

class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bank_id = Column(Integer, ForeignKey("banks.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    nickname = Column(String)
    number = Column(String, nullable=True)

    bank = relationship("Bank", back_populates="accounts")
    user = relationship("User", back_populates="accounts")
    transactions = relationship("Transaction", back_populates="account")
