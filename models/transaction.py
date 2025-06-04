from sqlalchemy import Column, Integer, String, Text, Date, DateTime, ForeignKey, Numeric, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime

from .base import Base

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    description = Column(Text, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    type = Column(String, nullable=False)  # 'income' or 'outcome'
    category = Column(String)
    balance = Column(Numeric(12, 2))
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    account = relationship("Account", back_populates="transactions")

    __table_args__ = (
        CheckConstraint("type IN ('income', 'outcome')", name="transactions_type_check"),
        UniqueConstraint("account_id", "date", "description", "amount", name="uq_transactions_unique_entry"),
    )
