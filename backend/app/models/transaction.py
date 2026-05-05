from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.db.database import Base

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    description = Column(String, index=True)
    amount = Column(Float)
    type = Column(String) # 'expense' or 'income'
    category = Column(String, index=True, nullable=True)
    date = Column(DateTime(timezone=True))
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
