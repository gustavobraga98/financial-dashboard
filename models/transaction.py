from sqlalchemy import Column, Integer, String, Text, Date, ForeignKey, Numeric, CheckConstraint
from sqlalchemy.orm import relationship

from .base import Base

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    description = Column(Text, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)  # Accepts negative and positive
    type = Column(String, nullable=False)  # Should be 'input' or 'output'
    category = Column(String)
    balance = Column(Numeric(12, 2))

    account = relationship("Account", back_populates="transactions")

    __table_args__ = (
        CheckConstraint("type IN ('input', 'output')", name="transactions_type_check"),
    )
